#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare a verified RK3399 image for an explicitly measured eMMC capacity.

Only ordinary files are opened. No USB, block-device, mounting or flashing code.
The seven partitions remain unchanged; only protective MBR/GPT geometry changes.
Run with the exact device-reported count of 512-byte logical sectors, not rounded MB.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import uuid
import zlib

SECTOR = 512
MIB = 1024 * 1024
BASE_BYTES = 12 * 1024 * MIB
MAX_TARGET_BYTES = 128 * 1024 * MIB
CHUNK = 4 * MIB
HEADER = struct.Struct('<8sIIIIQQQQ16sQIII')
EXPECTED = (
    ('boot', 16 * MIB, 256 * MIB),
    ('system', 272 * MIB, 4096 * MIB),
    ('system_ext', 4368 * MIB, 1024 * MIB),
    ('product', 5392 * MIB, 1024 * MIB),
    ('vendor', 6416 * MIB, 512 * MIB),
    ('metadata', 6928 * MIB, 32 * MIB),
    ('userdata', 6960 * MIB, 5327 * MIB),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(value):
    raw = str(value)
    require(not raw.startswith(('\\\\', '//')) and not raw.lower().startswith(('/dev/', '/proc/', '/sys/')),
            'Device, namespace and network paths are not allowed')
    path = Path(os.path.abspath(value))
    require(not str(path).lower().startswith(('/dev/', '/proc/', '/sys/')),
            'Device and pseudo-filesystem paths are not allowed')
    # Reject symlinks and Windows reparse points, including parent directories.
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Symlink/reparse paths are not allowed: ' + str(part))
    if os.name == 'nt':
        require(':' not in str(path)[2:], 'Alternate data streams are not allowed')
        require(not any(re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p, re.I)
                        for p in path.parts[1:]), 'Windows device names are not allowed')
    return path


def open_regular(path, create=False):
    if not create:
        require(stat.S_ISREG(os.lstat(path).st_mode), 'Only ordinary files are allowed')
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL if create else os.O_RDONLY
    flags |= getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags, 0o600)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'Only ordinary files are allowed')
        return os.fdopen(fd, 'w+b' if create else 'rb')
    except BaseException:
        os.close(fd)
        raise


def snapshot(stream):
    s = os.fstat(stream.fileno())
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def read_at(stream, offset, size):
    stream.seek(offset)
    value = stream.read(size)
    require(len(value) == size, 'Truncated file region')
    return value


def digest(stream, offset=0, size=None):
    if size is None:
        size = os.fstat(stream.fileno()).st_size - offset
    stream.seek(offset)
    result = hashlib.sha256()
    while size:
        chunk = stream.read(min(CHUNK, size))
        require(bool(chunk), 'Truncated file during hashing')
        result.update(chunk)
        size -= len(chunk)
    return result.hexdigest()


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(stream):
    require(os.fstat(stream.fileno()).st_size <= 16 * MIB, 'Oversized JSON input')
    stream.seek(0)
    return json.load(stream, object_pairs_hook=unique_json)


def read_gpt(stream, sectors):
    """Independent disk reader: validate both complete tables against file geometry."""
    require(os.fstat(stream.fileno()).st_size == sectors * SECTOR, 'File capacity mismatch')
    mbr = read_at(stream, 0, SECTOR)
    require(mbr[:446] == bytes(446) and mbr[462:510] == bytes(48)
            and mbr[510:] == b'\x55\xaa', 'Invalid protective MBR')
    m = struct.unpack_from('<B3sB3sII', mbr, 446)
    require(m[0] == 0 and m[2] == 0xEE and m[4:] == (1, sectors - 1), 'Protective MBR capacity mismatch')
    tables, headers = [], []
    for here, partner, table in ((1, sectors - 1, 2), (sectors - 1, 1, sectors - 33)):
        raw = read_at(stream, here * SECTOR, SECTOR)
        h = HEADER.unpack_from(raw)
        require(h[0:3] == (b'EFI PART', 0x10000, 92) and h[4] == 0
                and h[5:9] == (here, partner, 34, sectors - 34)
                and h[10:13] == (table, 128, 128) and raw[92:] == bytes(420), 'Invalid GPT geometry')
        checked = bytearray(raw[:92])
        struct.pack_into('<I', checked, 16, 0)
        require(zlib.crc32(checked) == h[3], 'GPT header CRC mismatch')
        entries = read_at(stream, table * SECTOR, 16384)
        require(zlib.crc32(entries) == h[13], 'GPT partition table CRC mismatch')
        headers.append(h)
        tables.append(entries)
    require(headers[0][9] != bytes(16) and headers[0][9] == headers[1][9]
            and tables[0] == tables[1], 'GPT copies differ')
    parts = []
    for i, (name, offset, size) in enumerate(EXPECTED):
        type_guid, ident, first, last, attrs, encoded = struct.unpack_from('<16s16sQQQ72s', tables[0], i * 128)
        actual_name = encoded.decode('utf-16-le').rstrip('\0')
        expected_type = 'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7' if name == 'boot' else '0fc63daf-8483-4772-8e79-3d69d8477de4'
        require(actual_name == name and first * SECTOR == offset and (last - first + 1) * SECTOR == size
                and attrs == 0 and ident != bytes(16) and str(uuid.UUID(bytes_le=type_guid)) == expected_type
                and 34 <= first <= last <= sectors - 34, 'Unexpected partition layout: ' + name)
        parts.append(dict(name=name, offset=offset, size=size, uuid=str(uuid.UUID(bytes_le=ident))))
    require(tables[0][len(EXPECTED) * 128:] == bytes(16384 - len(EXPECTED) * 128), 'Unexpected extra partitions')
    require(len({p['uuid'] for p in parts}) == 7, 'Duplicate partition UUIDs')
    return dict(mbr=mbr, header=headers[0], entries=tables[0], partitions=parts)


def target_header(original, here, partner, table, sectors):
    h = list(original)
    h[3], h[5], h[6], h[8], h[10] = 0, here, partner, sectors - 34, table
    h[3] = zlib.crc32(HEADER.pack(*h))
    return HEADER.pack(*h).ljust(SECTOR, b'\0')


def zero_region(stream, offset, size):
    stream.seek(offset)
    while size:
        count = min(CHUNK, size)
        require(stream.read(count) == bytes(count), 'Nonzero data in cleared/extended region')
        size -= count


def prepare(base_image, base_manifest, verification, target_sectors, output):
    require(type(target_sectors) is int and BASE_BYTES // SECTOR <= target_sectors <= MAX_TARGET_BYTES // SECTOR,
            'Target capacity must be between the base image and 128 GiB, in exact 512-byte sectors')
    paths = [safe_path(p) for p in (base_image, base_manifest, verification, output)]
    base_image, base_manifest, verification, output = paths
    report_path = output.with_suffix(output.suffix + '.json')
    partial = output.with_name(output.name + '.partial')
    report_partial = report_path.with_name(report_path.name + '.partial')
    require(output.parent.is_dir(), 'Output parent must already exist')
    for path in (output, report_path, partial, report_partial):
        safe_path(path)
        require(not os.path.lexists(path), 'Output already exists: ' + str(path))
    require(len(set(paths)) == 4, 'Input and output paths must differ')
    target_bytes = target_sectors * SECTOR
    with open_regular(base_image) as base, open_regular(base_manifest) as mf, open_regular(verification) as vf:
        before = [snapshot(f) for f in (base, mf, vf)]
        require(before[0][2] == BASE_BYTES, 'Base image must be exactly 12 GiB')
        manifest, verified = read_json(mf), read_json(vf)
        base_hash = digest(base)
        require(manifest.get('format') == 1 and manifest.get('board') == 'firefly,firefly-rk3399'
                and manifest.get('boot_medium') == 'emmc' and manifest.get('boot_device') == 'fe330000.mmc'
                and manifest.get('hardware_boot_verified') is False and manifest.get('image_size') == BASE_BYTES
                and manifest.get('image_sha256') == base_hash, 'Base manifest does not bind this RK3399 image')
        checks = verified.get('checks', [])
        require(verified.get('format') == 1 and verified.get('scope') == 'original-firefly-rk3399-emmc-offline'
                and verified.get('result') == 'PASS_OFFLINE_NOT_BOOTED' and verified.get('image_verified') is True
                and verified.get('image_sha256') == base_hash and verified.get('board_boot') == 'pending'
                and len(checks) > 0 and all(c.get('passed') is True for c in checks)
                and verified.get('checks_executed') == verified.get('checks_passed') == len(checks)
                and verified.get('checks_failed') == 0
                and {'image-size', 'image-target', 'whole-image-sha256', 'inputs-remained-unchanged'}
                <= {c.get('name') for c in checks}, 'A passing independent report for this exact base image is required')
        source = read_gpt(base, BASE_BYTES // SECTOR)
        require(len(manifest.get('partitions', [])) == 7, 'Base manifest must list seven partitions')
        for expected, recorded in zip(source['partitions'], manifest['partitions']):
            require(all(recorded.get(k) == expected[k] for k in ('name', 'offset', 'size', 'uuid')),
                    'Base manifest partition mismatch')
        input_hashes = [base_hash, digest(mf), digest(vf)]
        with open_regular(partial, create=True) as target:
            # New sparse holes read as zero on regular files; the result is a full raw image.
            target.truncate(target_bytes)
            base.seek(0)
            target.seek(0)
            while chunk := base.read(CHUNK):
                if chunk == bytes(len(chunk)):
                    target.seek(len(chunk), os.SEEK_CUR)
                else:
                    target.write(chunk)
            target.seek(BASE_BYTES - 33 * SECTOR)
            target.write(bytes(33 * SECTOR))
            mbr = bytearray(source['mbr'])
            struct.pack_into('<I', mbr, 458, target_sectors - 1)
            writes = ((0, mbr),
                      (SECTOR, target_header(source['header'], 1, target_sectors - 1, 2, target_sectors)),
                      ((target_sectors - 33) * SECTOR, source['entries']),
                      ((target_sectors - 1) * SECTOR,
                       target_header(source['header'], target_sectors - 1, 1, target_sectors - 33, target_sectors)))
            for offset, data in writes:
                target.seek(offset)
                target.write(data)
            target.flush()
            os.fsync(target.fileno())
        # Reopen read-only: independently parse the persisted bytes, not writer state.
        with open_regular(partial) as target:
            result_gpt = read_gpt(target, target_sectors)
            require(result_gpt['entries'] == source['entries'] and result_gpt['partitions'] == source['partitions'],
                    'Partition definitions changed')
            preserved_size = BASE_BYTES - 35 * SECTOR
            require(digest(base, 2 * SECTOR, preserved_size) == digest(target, 2 * SECTOR, preserved_size),
                    'Boot assets or partition bytes changed')
            gap_start = BASE_BYTES - 33 * SECTOR
            gap_end = (target_sectors - 33) * SECTOR
            zero_region(target, gap_start, gap_end - gap_start)
            parts = []
            for part in source['partitions']:
                source_hash = digest(base, part['offset'], part['size'])
                require(digest(target, part['offset'], part['size']) == source_hash, 'Partition content changed: ' + part['name'])
                parts.append(dict(part, sha256=source_hash))
            target_hash = digest(target)
        require(digest(base) == base_hash and [snapshot(f) for f in (base, mf, vf)] == before,
                'An input changed during target preparation')
        report = dict(format=1, result='PASS_TARGET_FILE_NOT_FLASHED',
                      created_at=datetime.now(timezone.utc).isoformat(), board='firefly,firefly-rk3399',
                      hardware_boot_verified=False, base_bytes=BASE_BYTES, base_sha256=base_hash,
                      base_manifest_sha256=input_hashes[1], verification_sha256=input_hashes[2],
                      inputs=dict(base_image=str(base_image), base_manifest=str(base_manifest), verification=str(verification)),
                      target_sectors=target_sectors, logical_sector_bytes=SECTOR, target_bytes=target_bytes,
                      target_sha256=target_hash, partitions=parts, userdata_resized=False,
                      gpt=dict(primary_lba=1, backup_lba=target_sectors - 1,
                               previous_backup_lba=BASE_BYTES // SECTOR - 1,
                               cleared_gap_offset=gap_start, cleared_gap_bytes=gap_end - gap_start),
                      checks=dict(primary_gpt_crc=True, backup_gpt_crc=True, backup_at_physical_end=True,
                                  partition_entries_identical=True, partition_bytes_identical=True,
                                  boot_assets_unchanged=True, old_backup_and_extension_zero=True,
                                  input_hash_rechecked=True))
    with open_regular(report_partial, create=True) as stream:
        stream.write((json.dumps(report, indent=2) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    # Exclusive hard-link publication also rejects a concurrently created destination.
    os.link(report_partial, report_path)
    try:
        os.link(partial, output)
    except BaseException:
        report_path.unlink()
        raise
    partial.unlink()
    report_partial.unlink()
    return report


def decimal_sectors(value):
    if not re.fullmatch(r'[0-9]+', value):
        raise argparse.ArgumentTypeError('Use an exact decimal count of 512-byte sectors')
    return int(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base-image', 'base-manifest', 'verification', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--target-sectors', type=decimal_sectors, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.base_image, args.base_manifest, args.verification, args.target_sectors, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        return 1
    print(json.dumps({key: result[key] for key in ('result', 'target_sectors', 'target_bytes', 'target_sha256')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
