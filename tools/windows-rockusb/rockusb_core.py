"""Offline-testable RK3399 protocol and whole-image verification core.

There is deliberately no live-device write CLI or Windows writer backend.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct

VID, PID = 0x2207, 0x330c
SECTOR_BYTES = 512
CHUNK_SECTORS = 256
LOADER_SHA256 = "1d2330a5eb5f638c7533464ca57018754157e65daf391e4f544befdd2b653929"
READ_FLASH_ID, READ_LBA, WRITE_LBA = 0x01, 0x14, 0x15
READ_FLASH_INFO, READ_CHIP_INFO, READ_STORAGE = 0x1a, 0x1b, 0x2b
READ_LENGTHS = {READ_FLASH_ID: 5, READ_FLASH_INFO: 11,
                READ_CHIP_INFO: 16, READ_STORAGE: 4}


def check_range(lba, sectors, capacity):
    if not (isinstance(lba, int) and isinstance(sectors, int)
            and 0 <= lba <= 0xffffffff and 1 <= sectors <= CHUNK_SECTORS
            and lba + sectors <= min(capacity, 0x100000000)):
        raise ValueError("LBA range exceeds observed capacity or 128 KiB transfer limit")


def cbw(opcode, *, tag=None, lba=0, sectors=0, capacity=0):
    if opcode not in (*READ_LENGTHS, READ_LBA, WRITE_LBA):
        raise ValueError("Unsupported command; reset, erase, RAM and recovery are absent")
    tag = secrets.randbits(32) if tag is None else tag
    if opcode in (READ_LBA, WRITE_LBA):
        check_range(lba, sectors, capacity)
        size, command_length = sectors * SECTOR_BYTES, 10
    else:
        size, command_length = READ_LENGTHS[opcode], 6
    result = bytearray(31)
    struct.pack_into("<III", result, 0, 0x43425355, tag, size)
    result[12] = 0 if opcode == WRITE_LBA else 0x80
    result[14], result[15] = command_length, opcode
    if command_length == 10:
        struct.pack_into(">I", result, 17, lba)
        struct.pack_into(">H", result, 22, sectors)
    return bytes(result), tag


def check_csw(raw, tag):
    if len(raw) != 13 or struct.unpack("<IIIB", raw) != (0x53425355, tag, 0, 0):
        raise IOError("CSW rejected (no legacy residue exception): " + raw.hex())


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identity_token(identity):
    return hashlib.sha256(json.dumps(identity, sort_keys=True,
                         separators=(",", ":")).encode()).hexdigest()


def confirmation(identity, image_sha256):
    return "WRITE RK3399 EMMC " + identity_token(identity)[:16] + " " + image_sha256[:16]


def whole_image(device, source, expected_sha256, identity, report, *,
                execute=False, confirm=None):
    """Use an injected transport; default is a read-only full-image comparison.

    A future hardware adapter must independently establish the identity and
    mapping evidence. Probe output intentionally cannot pass the write gate.
    The mock tests exercise this core; they do not validate physical hardware.
    """
    source, report = Path(source), Path(report)
    written = verified = 0
    with report.open("x", encoding="utf-8") as log:
        def emit(stage, **details):
            log.write(json.dumps(dict(stage=stage,
                      utc=datetime.now(timezone.utc).isoformat(), **details)) + "\n")
            log.flush()

        try:
            if identity.get("vid") != VID or identity.get("pid") != PID:
                raise ValueError("Identity is not RK3399 RockUSB")
            if identity.get("unique") is not True or identity.get("storage") != "emmc":
                raise ValueError("A unique eMMC target has not been established")
            if identity.get("sector_bytes") != SECTOR_BYTES:
                raise ValueError("Unexpected logical sector size")
            size = source.stat().st_size
            stamp = (size, source.stat().st_mtime_ns)
            capacity = identity.get("capacity_sectors", 0)
            if size == 0 or size % SECTOR_BYTES or size // SECTOR_BYTES > capacity:
                raise ValueError("Raw image is empty, unaligned or larger than target")
            if not 0 < capacity <= 0x100000000:
                raise ValueError("Capacity outside this LBA32 protocol")
            if len(expected_sha256) != 64 or sha256_file(source) != expected_sha256:
                raise ValueError("Source image SHA256 mismatch")
            if device.snapshot() != identity:
                raise RuntimeError("Device identity changed before operation")
            if execute:
                if (identity.get("physical_lba_verified") is not True
                        or identity.get("active_loader_verified") is not True
                        or identity.get("loader_sha256") != LOADER_SHA256):
                    raise ValueError("Live loader and physical LBA mapping evidence required")
                if confirm != confirmation(identity, expected_sha256):
                    raise ValueError("Explicit image-and-target confirmation missing")
            emit("validated", mode="write" if execute else "audit", identity=identity,
                 source=str(source.resolve()), source_bytes=size,
                 source_sha256=expected_sha256, reset_supported=False)
            sectors = size // SECTOR_BYTES
            positions = list(range(0, sectors, CHUNK_SECTORS))
            # Defer the first chunk containing GPT/boot headers; this is not an
            # atomic update or a guarantee that the old system remains bootable.
            if execute and len(positions) > 1:
                positions = positions[1:] + positions[:1]
            differences = 0
            with source.open("rb") as image:
                for lba in positions:
                    count = min(CHUNK_SECTORS, sectors - lba)
                    check_range(lba, count, capacity)
                    if device.snapshot() != identity:
                        raise RuntimeError("Device identity changed; no reconnect attempted")
                    stat = source.stat()
                    if (stat.st_size, stat.st_mtime_ns) != stamp:
                        raise RuntimeError("Source changed during operation")
                    image.seek(lba * SECTOR_BYTES)
                    expected = image.read(count * SECTOR_BYTES)
                    if len(expected) != count * SECTOR_BYTES:
                        raise IOError("Short source read")
                    if execute:
                        device.write_lba(lba, expected)
                        written += len(expected)
                        if device.snapshot() != identity:
                            raise RuntimeError("Device identity changed after write")
                    actual = device.read_lba(lba, count)
                    if len(actual) != len(expected):
                        raise IOError("Short device read")
                    if actual != expected:
                        differences += len(actual)
                        if execute:
                            raise IOError("Immediate readback mismatch at LBA " + hex(lba))
                    emit("block_verified" if execute else "block_compared", lba=lba,
                         bytes=len(actual), matches=actual == expected)
                if not execute:
                    stat = source.stat()
                    if (stat.st_size, stat.st_mtime_ns) != stamp or device.snapshot() != identity:
                        raise RuntimeError("Source or device identity changed at final audit gate")
                    emit("audit_complete", different_bytes=differences, media_written_bytes=0,
                         image_matches=differences == 0, physical_mapping_proven=False)
                    return
                digest = hashlib.sha256()
                for lba in range(0, sectors, CHUNK_SECTORS):
                    if device.snapshot() != identity:
                        raise RuntimeError("Device identity changed before final readback")
                    count = min(CHUNK_SECTORS, sectors - lba)
                    actual = device.read_lba(lba, count)
                    if len(actual) != count * SECTOR_BYTES:
                        raise IOError("Short final readback")
                    image.seek(lba * SECTOR_BYTES)
                    if actual != image.read(len(actual)):
                        raise IOError("Final byte comparison failed at LBA " + hex(lba))
                    digest.update(actual)
                    verified += len(actual)
                if digest.hexdigest() != expected_sha256:
                    raise IOError("Complete readback SHA256 differs from pinned source")
                stat = source.stat()
                if (stat.st_size, stat.st_mtime_ns) != stamp or device.snapshot() != identity:
                    raise RuntimeError("Source or device identity changed at final gate")
                emit("complete", written_bytes=written, verified_bytes=verified,
                     physical_readback_sha256=digest.hexdigest(),
                     image_extent_verified=True, unused_media_tail_verified=False,
                     reset_issued=False, automatic_retry=False)
                os.fsync(log.fileno())
        except BaseException as error:
            emit("failed", error=repr(error), written_bytes=written,
                 verified_bytes=verified, automatic_retry=False, reset_issued=False)
            raise
