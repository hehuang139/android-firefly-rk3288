#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
r"""Independently verify a Firefly-RK3288 Android 17 SD/eMMC raw image.

No mounts, loop devices, block devices, root privileges or assembler imports.
Filesystem tools operate on private copies of partition payloads. The image
and all build inputs are opened read-only. --check-tools is a preflight only;
it never produces an image-verification result.

Example:
  verify-sd.py --image android.img --product out/target/product/rk3288 \
    --boot-files boot-files --idbloader idbloader.img --uboot u-boot-dtb.img \
    --simg2img out/host/linux-x86/bin/simg2img --report verification.json
"""
import argparse
import codecs
from datetime import datetime, timezone
import fnmatch
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import uuid
import zlib


SECTOR = 512
MIB = 1024 * 1024
DISK_BYTES = 12 * 1024 * MIB
# Independently specified on-disk contract, in bytes. The final MiB is reserved
# for the backup GPT. This deliberately does not import assemble-sd.py.
EXPECTED = (
    ("boot", 16 * MIB, 256 * MIB),
    ("system", 272 * MIB, 4096 * MIB),
    ("system_ext", 4368 * MIB, 1024 * MIB),
    ("product", 5392 * MIB, 1024 * MIB),
    ("vendor", 6416 * MIB, 512 * MIB),
    ("metadata", 6928 * MIB, 32 * MIB),
    ("userdata", 6960 * MIB, 5327 * MIB),
)
BASIC_DATA = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"
LINUX_FS = "0fc63daf-8483-4772-8e79-3d69d8477de4"
CHUNK = 4 * MIB
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TOOLS = {
    "mcopy": ("-V",),
    "mdir": ("-V",),
    "fsck.fat": ("--help",),
    "e2fsck": ("-V",),
    "debugfs": ("-V",),
    "fdtget": ("--version",),
}
BOOT_MEDIA = {
    "sd": {"device": "ff0c0000.mmc", "emmc_status": "disabled", "sd_status": "okay",
           "bootcmd": "setenv boot_targets mmc1; bootflow scan -lb"},
    "emmc": {"device": "ff0f0000.mmc", "emmc_status": "okay", "sd_status": "disabled",
             "bootcmd": "mmc dev 0 && mmc rescan && sysboot mmc 0:1 any ${scriptaddr} /extlinux/extlinux.conf"},
}


class VerificationError(Exception):
    pass


def regular(path):
    """Check the resolved target before any tool is given an input pathname."""
    resolved = path.resolve(strict=True)
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise VerificationError("Input is not an ordinary file: " + str(path))
    return resolved


def snapshot(path):
    s = path.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def opened(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise VerificationError("Refusing a non-regular input: " + str(path))
    return os.fdopen(descriptor, "rb")


def digest(path, offset=0, length=None):
    result = hashlib.sha256()
    with opened(path) as stream:
        stream.seek(offset)
        remaining = length
        while remaining is None or remaining:
            block = stream.read(CHUNK if remaining is None else min(CHUNK, remaining))
            if not block:
                if remaining:
                    raise VerificationError("Truncated input: " + str(path))
                break
            result.update(block)
            if remaining is not None:
                remaining -= len(block)
    return result.hexdigest()


def read_at(path, offset, size):
    with opened(path) as stream:
        stream.seek(offset)
        data = stream.read(size)
    if len(data) != size:
        raise VerificationError("Truncated region at byte " + str(offset))
    return data


def zero_region(path, offset, length):
    with opened(path) as stream:
        stream.seek(offset)
        remaining = length
        while remaining:
            block = stream.read(min(remaining, CHUNK))
            if not block:
                raise VerificationError("Truncated zero-fill region")
            if block.count(0) != len(block):
                return False
            remaining -= len(block)
    return True


def extract_region(image, target, offset, length):
    """Make a private sparse copy, computing a hash from the actual image."""
    result = hashlib.sha256()
    with opened(image) as source, target.open("xb") as dest:
        source.seek(offset)
        remaining = length
        while remaining:
            data = source.read(min(remaining, CHUNK))
            if not data:
                raise VerificationError("Truncated partition payload")
            result.update(data)
            if data.count(0) == len(data):
                dest.seek(len(data), os.SEEK_CUR)
            else:
                dest.write(data)
            remaining -= len(data)
        dest.truncate(length)
    return result.hexdigest()


def command(*args, timeout=1800):
    return subprocess.run([str(value) for value in args], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout, check=False)


def output(result):
    return (result.stdout + result.stderr).decode("utf-8", errors="replace")[-6000:]


class Audit:
    def __init__(self, scope):
        self.data = {"format": 1, "scope": scope, "started_at": now(),
                     "image_verified": False, "board_boot": "pending", "checks": []}
        self.stage = "preflight"

    def check(self, name, condition, detail=None):
        record = {"stage": self.stage, "name": name, "passed": bool(condition)}
        if detail is not None:
            record["detail"] = detail
        self.data["checks"].append(record)
        if not condition:
            raise VerificationError(name)

    def run(self, name, *args):
        result = command(*args)
        self.check(name, result.returncode == 0,
                   {"command": [str(v) for v in args], "exit_code": result.returncode,
                    "output": output(result)})
        return result

    def finish(self, result):
        checks = self.data["checks"]
        self.data.update(result=result, finished_at=now(), checks_executed=len(checks),
                         checks_passed=sum(item["passed"] for item in checks),
                         checks_failed=sum(not item["passed"] for item in checks))


def now():
    return datetime.now(timezone.utc).isoformat()


def preflight(audit):
    for name, flags in TOOLS.items():
        location = shutil.which(name)
        audit.check("tool-present:" + name, location is not None, location)
        result = command(location, *flags, timeout=30)
        audit.check("tool-runs:" + name, result.returncode == 0,
                    {"path": location, "exit_code": result.returncode,
                     "version_or_help": output(result)[:1200]})


def parse_gpt(image, audit):
    audit.stage = "gpt"
    sectors = DISK_BYTES // SECTOR
    mbr = read_at(image, 0, SECTOR)
    audit.check("protective-mbr-signature", mbr[510:] == b"\x55\xaa")
    first = struct.unpack("<B3sB3sII", mbr[446:462])
    audit.check("protective-mbr-entry", first[0] == 0 and first[2] == 0xEE
                and first[4:] == (1, sectors - 1), list(first[4:]))
    audit.check("protective-mbr-exclusive", mbr[:446] == bytes(446)
                and mbr[462:510] == bytes(48))

    def header(lba, partner, table, label):
        raw = read_at(image, lba * SECTOR, SECTOR)
        fields = struct.unpack_from("<8sIIIIQQQQ16sQIII", raw)
        (magic, revision, size, crc, reserved, current, backup, first_usable,
         last_usable, disk_guid, entry_lba, count, entry_size, entries_crc) = fields
        audit.check(label + ":header-fields", magic == b"EFI PART"
                    and revision == 0x10000 and size == 92 and reserved == 0
                    and current == lba and backup == partner
                    and first_usable == 34 and last_usable == sectors - 34
                    and entry_lba == table and count == 128 and entry_size == 128,
                    {"current_lba": current, "backup_lba": backup,
                     "entries_lba": entry_lba, "count": count, "entry_size": entry_size})
        copied = bytearray(raw[:size])
        copied[16:20] = bytes(4)
        audit.check(label + ":header-crc32", zlib.crc32(copied) == crc,
                    {"stored": crc, "computed": zlib.crc32(copied)})
        audit.check(label + ":header-padding", raw[size:] == bytes(SECTOR - size))
        entries = read_at(image, entry_lba * SECTOR, count * entry_size)
        audit.check(label + ":entries-crc32", zlib.crc32(entries) == entries_crc,
                    {"stored": entries_crc, "computed": zlib.crc32(entries)})
        return disk_guid, entries

    primary_guid, entries = header(1, sectors - 1, 2, "primary")
    backup_guid, backup_entries = header(sectors - 1, 1, sectors - 33, "backup")
    audit.check("gpt-disk-guid", primary_guid == backup_guid and primary_guid != bytes(16),
                str(uuid.UUID(bytes_le=primary_guid)))
    audit.check("gpt-entry-copies-identical", entries == backup_entries)
    audit.check("gpt-unused-entries-zero", entries[7 * 128:] == bytes(121 * 128))
    result = []
    identifiers = set()
    previous_end = 16 * MIB
    for i, (name, expected_start, expected_size) in enumerate(EXPECTED):
        type_guid, ident, start, end, attrs, encoded_name = struct.unpack_from(
            "<16s16sQQQ72s", entries, i * 128)
        decoded = encoded_name.decode("utf-16-le")
        actual_name, _, padding = decoded.partition("\0")
        offset, length = start * SECTOR, (end - start + 1) * SECTOR
        actual_type = str(uuid.UUID(bytes_le=type_guid))
        audit.check("partition-layout:" + name, actual_name == name
                    and not padding.strip("\0") and offset == expected_start
                    and length == expected_size and attrs == 0,
                    {"name": actual_name, "offset": offset, "size": length, "attributes": attrs})
        audit.check("partition-type:" + name,
                    actual_type == (BASIC_DATA if name == "boot" else LINUX_FS), actual_type)
        audit.check("partition-alignment-and-bounds:" + name,
                    offset % MIB == 0 and length % MIB == 0 and offset >= previous_end
                    and start >= 34 and end <= sectors - 34 and end >= start)
        audit.check("partition-unique-guid:" + name, ident != bytes(16) and ident not in identifiers)
        identifiers.add(ident)
        previous_end = offset + length
        result.append({"name": name, "offset": offset, "size": length,
                       "uuid": str(uuid.UUID(bytes_le=ident))})
    audit.data["gpt"] = {"disk_uuid": str(uuid.UUID(bytes_le=primary_guid)), "partitions": result}
    return result


def rc4(data):
    key = bytes((124, 78, 3, 4, 85, 5, 9, 7, 45, 44, 123, 56, 23, 13, 23, 17))
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) & 255
        state[i], state[j] = state[j], state[i]
    result = bytearray()
    i = j = 0
    for value in data:
        i = (i + 1) & 255
        j = (j + state[i]) & 255
        state[i], state[j] = state[j], state[i]
        result.append(value ^ state[(state[i] + state[j]) & 255])
    return result


def check_boot_medium_loaders(idb_data, uboot_data, boot_medium, audit, scratch):
    matches = re.findall(rb"(?:^|\x00)bootcmd=([^\x00]+)\x00", uboot_data)
    expected = BOOT_MEDIA[boot_medium]["bootcmd"]
    audit.check("uboot:boot-medium-command", matches == [expected.encode("ascii")],
                {"boot_medium": boot_medium, "expected": expected,
                 "values": [value.decode("ascii", errors="replace") for value in matches]})
    if boot_medium != "emmc":
        return
    # Validate the eMMC-only SPL policy in the actual idbloader disk bytes.
    # Do not accept a correctly named file containing the SD loader instead.
    orders, candidates, offset = [], [], 0
    while (offset := idb_data.find(b"\xd0\x0d\xfe\xed", offset)) >= 0:
        position = offset
        offset += 4
        if position + 40 > len(idb_data):
            continue
        header = struct.unpack_from(">10I", idb_data, position)
        _, length, structs, strings, reserve, version, compatible, _, string_size, struct_size = header
        if not (40 <= length <= len(idb_data) - position and version == 17 and compatible <= 17
                and 40 <= structs <= length and 40 <= strings <= length and 40 <= reserve < length
                and structs + struct_size <= length and strings + string_size <= length):
            continue
        path = scratch / ("idbloader-spl-" + str(position) + ".dtb")
        path.write_bytes(idb_data[position:position + length])
        result = command("fdtget", "-t", "s", path, "/chosen", "u-boot,spl-boot-order")
        candidate = {"offset": position, "bytes": length, "sha256": digest(path), "property_exit_code": result.returncode}
        if result.returncode == 0:
            order = result.stdout.decode("utf-8").split()
            candidate["spl_boot_order"] = order
            orders.append(order)
        candidates.append(candidate)
    audit.check("idbloader:emmc-only-spl-boot-order", orders == [["/mmc@ff0f0000"]], candidates)


def verify_loaders(image, idb, uboot, audit, boot_medium="sd", scratch=None):
    audit.stage = "loaders"
    for name, source, offset, limit in (
            ("idbloader", idb, 32 * 1024, 8 * MIB),
            ("uboot", uboot, 8 * MIB, 16 * MIB)):
        length = source.stat().st_size
        audit.check(name + ":fits-reserved-region", 0 < length <= limit - offset, length)
        actual = digest(image, offset, length)
        expected = digest(source)
        audit.check(name + ":input-bytes", actual == expected,
                    {"offset": offset, "bytes": length, "sha256": actual, "expected": expected})
        audit.check(name + ":reserved-tail-zero", zero_region(image, offset + length,
                                                              limit - offset - length))
    header = rc4(read_at(image, 32 * 1024, 512))
    magic, disable_rc4 = struct.unpack_from("<I", header)[0], struct.unpack_from("<I", header, 8)[0]
    init_offset = struct.unpack_from("<H", header, 12)[0]
    init_size, boot_size = struct.unpack_from("<HH", header, 506)
    audit.check("idbloader:rockchip-v1-header", magic == 0x0FF0AA55 and disable_rc4 == 1
                and init_offset == 4 and 0 < init_size <= 64 and boot_size > init_size
                and (init_offset + boot_size) * SECTOR == idb.stat().st_size,
                {"decoded_magic": hex(magic), "payload_rc4_disabled": disable_rc4,
                 "init_offset_sectors": init_offset, "init_sectors": init_size,
                 "total_payload_sectors": boot_size,
                 "checksum": "Rockchip v1 has no payload CRC; full input SHA-256 checked"})
    audit.check("idbloader:rk3288-code-marker",
                read_at(image, 32 * 1024 + init_offset * SECTOR, 4) == b"RK32")
    legacy = read_at(image, 8 * MIB, 64)
    values = struct.unpack(">7I4B32s", legacy)
    magic, header_crc, _, size, _, _, data_crc, os_id, arch, kind, compression, name = values
    audit.check("uboot:legacy-arm-firmware-header", magic == 0x27051956
                and os_id == 17 and arch == 2 and kind == 5 and compression == 0
                and size + 64 == uboot.stat().st_size,
                {"payload_bytes": size, "os": os_id, "arch": arch, "type": kind,
                 "compression": compression, "name": name.rstrip(b"\0").decode(errors="replace")})
    copied = bytearray(legacy)
    copied[4:8] = bytes(4)
    audit.check("uboot:header-crc32", zlib.crc32(copied) == header_crc)
    checksum = 0
    with opened(image) as stream:
        stream.seek(8 * MIB + 64)
        remaining = size
        while remaining:
            data = stream.read(min(CHUNK, remaining))
            if not data:
                raise VerificationError("Truncated U-Boot payload")
            checksum = zlib.crc32(data, checksum)
            remaining -= len(data)
    audit.check("uboot:payload-crc32", checksum == data_crc,
                {"stored": data_crc, "computed": checksum})
    check_boot_medium_loaders(read_at(image, 32 * 1024, idb.stat().st_size),
                              read_at(image, 8 * MIB, uboot.stat().st_size),
                              boot_medium, audit, scratch)
    audit.check("primary-gpt-to-loader-gap-zero",
                zero_region(image, 34 * SECTOR, 32 * 1024 - 34 * SECTOR))
    audit.check("userdata-to-backup-gpt-gap-zero",
                zero_region(image, DISK_BYTES - MIB, MIB - 33 * SECTOR))


def elf_info(path, *, installed_path=None):
    length = path.stat().st_size
    with opened(path) as stream:
        raw = stream.read(52)
        if len(raw) != 52 or raw[:7] != b"\x7fELF\x01\x01\x01":
            raise VerificationError("Not a little-endian ARM32 ELF: " + str(path))
        fields = struct.unpack("<16sHHIIIIIHHHHHH", raw)
        _, kind, machine, version, _, phoff, _, flags, ehsize, phsize, phcount, _, _, _ = fields
        if (kind not in (2, 3) or machine != 40 or version != 1 or ehsize != 52
                or flags >> 24 != 5 or phsize != 32 or not phcount
                or phoff + phsize * phcount > length):
            raise VerificationError("Invalid ARM EABI5 executable/shared library header: " + str(path))
        stream.seek(phoff)
        executable_load = False
        interpreter = None
        for _ in range(phcount):
            ptype, offset, _, _, filesz, memsz, pflags, _ = struct.unpack("<8I", stream.read(32))
            if ptype in (1, 3) and (offset + filesz > length or (ptype == 1 and filesz > memsz)):
                raise VerificationError("ELF program segment exceeds file: " + str(path))
            if ptype == 1 and pflags & 1:
                executable_load = True
            if ptype == 3:
                position = stream.tell()
                stream.seek(offset)
                interpreter = stream.read(filesz).rstrip(b"\0").decode()
                stream.seek(position)
        allowed_interpreters = (None, "/system/bin/linker")
        # AOSP init is marked bootstrap: true and must run before the runtime
        # APEX is mounted. Soong selects this linker only for bootstrap binaries.
        # Grant the exception to the resolved installed init path, never its
        # temporary exported basename or arbitrary vendor/system binaries.
        if installed_path == "/system/bin/init":
            allowed_interpreters += ("/system/bin/bootstrap/linker",)
        if not executable_load or interpreter not in allowed_interpreters:
            raise VerificationError("Invalid ARM32 load segments/interpreter: " + str(path))
    return {"class": "ELF32", "machine": "ARM", "eabi": 5, "type": kind,
            "interpreter": interpreter, "bytes": length, "sha256": digest(path)}


def parse_cpio(data, *, duplicate_directories=None):
    """Parse newc, allowing only idempotent repetitions of empty directories.

    mkbootfs can emit the same directory more than once when merging roots.
    Linux initramfs accepts these and reapplies directory metadata; c_ino is
    not used for directories. Require every other semantic header field to
    match, and continue rejecting all repeated files and conflicting metadata.
    """
    position = 0
    entries = {}
    directory_metadata = {}
    while position + 110 <= len(data):
        magic = data[position:position + 6]
        if magic not in (b"070701", b"070702"):
            raise VerificationError("Ramdisk is not a newc cpio archive")
        fields = [int(data[position + 6 + i * 8:position + 14 + i * 8], 16)
                  for i in range(13)]
        size, name_size = fields[6], fields[11]
        name_end = position + 110 + name_size
        if not name_size or name_end > len(data) or data[name_end - 1] != 0:
            raise VerificationError("Truncated cpio filename")
        name = data[position + 110:name_end - 1].decode("utf-8")
        if name.startswith("./"):
            name = name[2:]
        start = (name_end + 3) & ~3
        if start + size > len(data):
            raise VerificationError("Truncated cpio data")
        payload = data[start:start + size]
        position = (start + size + 3) & ~3
        if name == "TRAILER!!!":
            if data[position:].strip(b"\0"):
                raise VerificationError("Unexpected data after cpio trailer")
            return entries
        if (name.startswith("/") or ".." in name.split("/")
                or "\0" in name or (magic == b"070702" and sum(payload) & 0xFFFFFFFF != fields[12])
                or (magic == b"070701" and fields[12] != 0)):
            raise VerificationError("Invalid or duplicate cpio member: " + name)
        metadata = tuple(fields[1:11])
        if name in entries:
            if (not stat.S_ISDIR(fields[1]) or payload
                    or directory_metadata.get(name) != metadata):
                raise VerificationError("Invalid or duplicate cpio member: " + name)
            if duplicate_directories is not None:
                duplicate_directories.append(name)
            continue
        entries[name] = {"mode": fields[1], "uid": fields[2], "gid": fields[3], "data": payload}
        if stat.S_ISDIR(fields[1]) and not payload:
            directory_metadata[name] = metadata
    raise VerificationError("Missing cpio trailer")


def check_fstab(data, audit, name):
    expected = {"system": "/system", "system_ext": "/system_ext", "product": "/product",
                "vendor": "/vendor", "metadata": "/metadata", "userdata": "/data"}
    found = {}
    for line in data.decode("utf-8").splitlines():
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        if len(fields) != 5:
            raise VerificationError("Invalid fstab record: " + line)
        source, mountpoint, filesystem, mountflags, fsflags = fields
        if source == "/dev/block/zram0" and filesystem == "swap":
            continue
        prefix = "/dev/block/by-name/"
        if not source.startswith(prefix):
            raise VerificationError("Unexpected fstab device: " + source)
        part = source[len(prefix):]
        if part not in expected or part in found:
            raise VerificationError("Unexpected/duplicate fstab partition: " + part)
        found[part] = (mountpoint, filesystem, set(mountflags.split(",")), set(fsflags.split(",")))
    for part, mountpoint in expected.items():
        fields = found.get(part)
        valid = fields is not None and fields[0] == mountpoint and fields[1] == "ext4"
        if valid:
            flags = fields[3]
            valid = "wait" in flags and not any(
                flag.startswith(("fileencryption", "metadata_encryption", "keydirectory", "avb", "logical"))
                for flag in flags)
            valid = valid and (("latemount" in flags) if part == "userdata" else ("first_stage_mount" in flags))
            if part in ("system", "system_ext", "product", "vendor"):
                valid = valid and "ro" in fields[2]
        audit.check(name + ":" + part, valid, {"mountpoint": fields[0], "type": fields[1],
                    "mount_flags": sorted(fields[2]), "fs_mgr_flags": sorted(fields[3])} if fields else None)


def check_boot_load_windows(extracted, uboot, audit):
    # extlinux/bootz uses U-Boot's environment, not boot.img offsets. Inspect
    # the actual loader input whose disk payload was already hash-checked.
    with opened(uboot) as stream:
        binary = stream.read()
    expected = {"fdt_addr_r": 0x01F00000, "kernel_addr_r": 0x02000000,
                "ramdisk_addr_r": 0x04000000, "fdt_high": 0x0FFFFFFF,
                "initrd_high": 0x0FFFFFFF}
    environment = {}
    for key, value in expected.items():
        matches = re.findall(rb"(?:^|\x00)" + key.encode("ascii") + rb"=([^\x00]+)\x00", binary)
        audit.check("uboot-load-environment:" + key,
                    len(matches) == 1 and re.fullmatch(rb"(?:0x)?[0-9a-fA-F]+", matches[0])
                    and int(matches[0], 16) == value,
                    {"values": [match.decode("ascii", errors="replace") for match in matches],
                     "expected": hex(value)})
        environment[key] = value
    windows = (("boot/rk3288-firefly-android.dtb", "fdt_addr_r", environment["kernel_addr_r"]),
               ("boot/zImage", "kernel_addr_r", environment["ramdisk_addr_r"]),
               ("boot/ramdisk.img", "ramdisk_addr_r", environment["initrd_high"]))
    report = {"environment": {key: hex(value) for key, value in environment.items()},
              "loaded_files": {}}
    audit.data["boot_load_windows"] = report
    for path, key, limit in windows:
        size, start = extracted[path].stat().st_size, environment[key]
        detail = {"bytes": size, "load_address": hex(start), "end_exclusive": hex(start + size),
                  "window_end": hex(limit), "available_bytes": limit - start}
        report["loaded_files"][path] = detail
        audit.check("uboot-load-window:" + path, 0 < size <= limit - start, detail)
    # bootz reserves zi_end-zi_start from the zImage header. Match that span
    # to the actual file, rather than trusting just its magic or FAT length.
    kernel = extracted["boot/zImage"]
    start, end = struct.unpack("<2I", read_at(kernel, 40, 8))
    audit.check("arm-zimage-reserved-length", start == 0 and end == kernel.stat().st_size,
                {"header_start": start, "header_end": end, "file_bytes": kernel.stat().st_size})


def check_boot_medium_files(dtb, config, boot_medium, audit):
    medium = BOOT_MEDIA[boot_medium]
    properties = (("/", "compatible", "firefly,firefly-rk3288"),
                  ("/mmc@ff0f0000", "status", medium["emmc_status"]),
                  ("/mmc@ff0c0000", "status", medium["sd_status"]),
                  ("/hdmi@ff980000", "status", "okay"),
                  ("/gpu@ffa30000", "status", "okay"),
                  ("/usb@ff580000", "dr_mode", "peripheral"))
    for node, prop, expected in properties:
        result = command("fdtget", "-t", "s", dtb, node, prop)
        values = result.stdout.decode("utf-8").strip().split()
        audit.check("actual-dtb:" + node + ":" + prop,
                    result.returncode == 0 and expected in values,
                    {"values": values, "exit_code": result.returncode})
    if boot_medium == "emmc":
        result = command("fdtget", "-t", "u", dtb, "/mmc@ff0f0000", "max-frequency")
        audit.check("actual-dtb:emmc-max-frequency", result.returncode == 0
                    and result.stdout.decode("ascii").split() == ["50000000"], output(result))
    directives = {}
    for line in config.splitlines():
        fields = line.split("#", 1)[0].strip().split(None, 1)
        if len(fields) == 2:
            directives.setdefault(fields[0].upper(), []).append(fields[1].strip())
    for key, value in (("LINUX", "/boot/zImage"), ("INITRD", "/boot/ramdisk.img"),
                       ("FDT", "/boot/rk3288-firefly-android.dtb")):
        audit.check("extlinux:" + key, directives.get(key) == [value], directives.get(key))
    append = directives.get("APPEND", [])
    audit.check("extlinux:one-command-line", len(append) == 1, append)
    arguments = append[0].split()
    for token in ("androidboot.hardware=fireflyrk3288", "androidboot.boot_devices=" + medium["device"]):
        audit.check("extlinux:" + token, arguments.count(token) == 1)
    audit.check("extlinux:single-boot-medium",
                [token for token in arguments if token.startswith("androidboot.boot_devices=")]
                == ["androidboot.boot_devices=" + medium["device"]], arguments)


def verify_fat(fat, source_dir, scratch, audit, uboot, boot_medium="sd"):
    audit.stage = "fat-and-boot"
    boot = read_at(fat, 0, 512)
    audit.check("fat32-boot-sector", boot[510:] == b"\x55\xaa"
                and struct.unpack_from("<H", boot, 11)[0] == 512
                and struct.unpack_from("<I", boot, 32)[0] * SECTOR == 256 * MIB
                and boot[82:90] == b"FAT32   " and boot[71:82] == b"FIREFLYBOOT")
    audit.run("fat32-readonly-fsck", "fsck.fat", "-n", fat)
    sources = {str(p.relative_to(source_dir)): regular(p)
               for p in source_dir.rglob("*") if p.is_file()}
    mandatory = {"boot/zImage", "boot/ramdisk.img", "boot/rk3288-firefly-android.dtb",
                 "extlinux/extlinux.conf"}
    audit.check("required-boot-source-files", mandatory <= sources.keys(), sorted(sources))
    listing = audit.run("fat-file-inventory-command", "mdir", "-a", "-/", "-b", "-i", fat, "::/")
    actual = set()
    for line in listing.stdout.decode("utf-8").splitlines():
        if line.startswith("::/") and not line.endswith("/"):
            actual.add(line[3:].casefold())
    audit.check("fat-file-inventory", actual == {p.casefold() for p in sources}, sorted(actual))
    extracted = {}
    for i, (relative, source) in enumerate(sorted(sources.items())):
        if any(c in relative for c in "\r\n*?[]"):
            raise VerificationError("Unsupported FAT filename: " + relative)
        dest = scratch / ("fat-file-" + str(i))
        audit.run("fat-extract:" + relative, "mcopy", "-i", fat, "::/" + relative, dest)
        expected_hash = digest(source)
        actual_hash = digest(dest)
        audit.check("fat-file-input-bytes:" + relative, expected_hash == actual_hash,
                    {"bytes": dest.stat().st_size, "sha256": actual_hash, "expected": expected_hash})
        extracted[relative] = dest
    kernel = extracted["boot/zImage"]
    audit.check("arm-zimage-magic", read_at(kernel, 36, 4) == b"\x18\x28\x6f\x01")
    check_boot_load_windows(extracted, uboot, audit)
    dtb = extracted["boot/rk3288-firefly-android.dtb"]
    check_boot_medium_files(dtb, extracted["extlinux/extlinux.conf"].read_text(), boot_medium, audit)
    with gzip.GzipFile(fileobj=io.BytesIO(extracted["boot/ramdisk.img"].read_bytes())) as stream:
        raw = stream.read(512 * MIB + 1)
    audit.check("ramdisk-bounded-gzip", len(raw) <= 512 * MIB, len(raw))
    duplicate_directories = []
    entries = parse_cpio(raw, duplicate_directories=duplicate_directories)
    init = entries.get("init", {})
    audit.check("ramdisk-root-init-executable", stat.S_ISREG(init.get("mode", 0))
                and init.get("mode", 0) & 0o111 and init.get("uid") == 0 and init.get("gid") == 0)
    init_path = scratch / "first-stage-init"
    init_path.write_bytes(init["data"])
    audit.check("ramdisk-init-arm32", True, elf_info(init_path))
    fstab = entries.get("fstab.fireflyrk3288", {})
    audit.check("ramdisk-board-fstab", stat.S_ISREG(fstab.get("mode", 0)))
    check_fstab(fstab["data"], audit, "ramdisk-fstab")
    audit.data["ramdisk"] = {"cpio_members": len(entries), "uncompressed_bytes": len(raw),
                             "identical_empty_directory_repetitions": duplicate_directories,
                             "compressed_bytes": extracted["boot/ramdisk.img"].stat().st_size}


def quote_debugfs(text):
    if any(c in text for c in "\x00\r\n"):
        raise VerificationError("Unsupported control character in filesystem path")
    # libss quotes use doubled double quotes; backslashes stay literal.
    return '"' + text.replace('"', '""') + '"'


class Ext4:
    def __init__(self, image, scratch, mount_prefix):
        self.image, self.scratch, self.mount_prefix = image, scratch, mount_prefix
        self.counter, self.cache = 0, {}

    def debug(self, request):
        result = command("debugfs", "-R", request, self.image)
        error = result.stderr.decode(errors="replace")
        if any(s in error for s in ("File not found", "not a directory", "Not a directory")):
            raise FileNotFoundError(request)
        diagnostics = [line for line in error.splitlines()
                       if line.strip() and not re.match(r"^debugfs\s+[0-9]", line)]
        if result.returncode or diagnostics or "Usage:" in result.stdout.decode(errors="replace"):
            raise VerificationError("debugfs failed: " + request + "\n" + output(result))
        return result.stdout

    def inode(self, path):
        if path not in self.cache:
            data = self.debug("stat " + quote_debugfs(path)).decode(errors="replace")
            match = re.search(r"Type:\s*(\S+)\s+Mode:\s*([0-7]+)", data)
            owner = re.search(r"User:\s*(\d+)\s+Group:\s*(\d+)", data)
            size = re.search(r"Size:\s*(\d+)", data)
            number = re.search(r"Inode:\s*(\d+)", data)
            links = re.search(r"Links:\s*(\d+)", data)
            if not match or not owner or not size or not number or not links:
                raise VerificationError("Cannot parse inode metadata for " + path + "\n" + data)
            target = re.search(r'Fast link dest:\s*"(.*)"', data)
            self.cache[path] = {"type": match[1], "mode": int(match[2], 8),
                                "uid": int(owner[1]), "gid": int(owner[2]), "size": int(size[1]),
                                "link": target[1] if target else None,
                                "inode": int(number[1]), "links": int(links[1])}
        return self.cache[path]

    def resolve(self, path):
        queue = posixpath.normpath("/" + path.lstrip("/")).strip("/").split("/")
        current, followed = "/", 0
        while queue:
            component = queue.pop(0)
            if not component:
                continue
            candidate = posixpath.join(current, component)
            inode = self.inode(candidate)
            if inode["type"] == "symlink":
                target = inode["link"]
                if target is None:
                    target = self.debug("cat " + quote_debugfs(candidate)).decode("utf-8")
                if target.startswith("/"):
                    prefix = "/" + self.mount_prefix + "/" if self.mount_prefix else None
                    if prefix and target.startswith(prefix):
                        target = target[len(prefix) - 1:]
                    destination = target
                else:
                    destination = posixpath.join(current, target)
                queue = posixpath.normpath(destination).strip("/").split("/") + queue
                current = "/"
                followed += 1
                if followed > 40:
                    raise VerificationError("Filesystem symlink loop: " + path)
            else:
                current = candidate
        return current

    def exists(self, path):
        try:
            self.resolve(path)
            return True
        except FileNotFoundError:
            return False

    def read(self, path):
        return self.debug("cat " + quote_debugfs(self.resolve(path)))

    def dump(self, path):
        actual = self.resolve(path)
        if self.inode(actual)["type"] != "regular":
            raise VerificationError("Expected a regular filesystem member: " + path)
        self.counter += 1
        dest = self.scratch / (self.image.stem + "-member-" + str(self.counter))
        self.debug("dump " + quote_debugfs(actual) + " " + quote_debugfs(str(dest)))
        regular(dest)
        if dest.stat().st_size != self.inode(actual)["size"]:
            raise VerificationError("debugfs dumped an incomplete member: " + path)
        return actual, dest

    def xattrs(self, path):
        # ea_list may abbreviate values in its human-readable output. Retrieve
        # every complete value to a private regular file with ea_get -f.
        result = {}
        listing = self.debug("ea_list " + quote_debugfs(path)).decode("utf-8")
        for line in listing.splitlines():
            if not line or line == "Extended attributes:":
                continue
            match = re.fullmatch(r"  (.+) \((\d+)\)(?: = .*)?", line)
            if not match:
                raise VerificationError("Cannot parse xattr listing: " + line)
            name = codecs.escape_decode(match[1].encode("utf-8"))[0].decode("utf-8")
            size = int(match[2])
            self.counter += 1
            target = self.scratch / (self.image.stem + "-xattr-" + str(self.counter))
            self.debug("ea_get -f " + quote_debugfs(str(target)) + " "
                       + quote_debugfs(path) + " " + quote_debugfs(name))
            regular(target)
            if target.stat().st_size != size or name in result:
                raise VerificationError("Incomplete or duplicate xattr: " + path + " " + name)
            result[name] = {"bytes": size, "sha256": digest(target)}
            target.unlink()
        return result

    def inventory(self):
        result, queue, hardlinks = {}, ["/"], {}
        while queue:
            directory = queue.pop()
            metadata = self.inode(directory)
            result[directory] = {k: metadata[k] for k in ("type", "mode", "uid", "gid", "links")}
            result[directory]["xattrs"] = self.xattrs(directory)
            listing = self.debug("ls -p " + quote_debugfs(directory)).decode("utf-8")
            for line in listing.splitlines():
                if not line.startswith("/"):
                    continue
                fields = line.split("/")
                if len(fields) < 8:
                    raise VerificationError("Cannot parse debugfs directory record")
                # debugfs ls includes free directory slots, notably in
                # mkfs-created lost+found. Inode zero is not a member.
                if fields[1] == "0":
                    continue
                name = fields[5]
                if name in (".", ".."):
                    continue
                if not name or any(c in name for c in "\x00\r\n"):
                    raise VerificationError("Invalid filesystem directory member")
                path = posixpath.join(directory, name)
                metadata = self.inode(path)
                record = {k: metadata[k] for k in ("type", "mode", "uid", "gid", "links")}
                record["xattrs"] = self.xattrs(path)
                if metadata["type"] == "directory":
                    queue.append(path)
                elif metadata["type"] == "regular":
                    hardlinks.setdefault(metadata["inode"], []).append(path)
                    _, exported = self.dump(path)
                    record.update(bytes=exported.stat().st_size, sha256=digest(exported))
                    exported.unlink()
                elif metadata["type"] == "symlink":
                    record["target"] = metadata["link"] if metadata["link"] is not None else self.debug(
                        "cat " + quote_debugfs(path)).decode("utf-8")
                else:
                    raise VerificationError("Unexpected special file in initial userdata: " + path)
                result[path] = record
                if len(result) > 500000:
                    raise VerificationError("Unexpectedly large initial userdata inventory")
        for paths in hardlinks.values():
            for path in paths:
                result[path]["hardlink_paths"] = sorted(paths)
        return result


def superblock(path):
    data = read_at(path, 1024, 1024)
    if data[56:58] != b"\x53\xef":
        raise VerificationError("Not an ext4 filesystem: " + str(path))
    log_block_size = struct.unpack_from("<I", data, 24)[0]
    if log_block_size > 6:
        raise VerificationError("Invalid ext4 block size")
    block_size = 1024 << log_block_size
    blocks = struct.unpack_from("<I", data, 4)[0]
    if struct.unpack_from("<I", data, 96)[0] & 0x80:
        blocks |= struct.unpack_from("<I", data, 336)[0] << 32
    return {"uuid": str(uuid.UUID(bytes=data[104:120])), "block_bytes": block_size,
            "filesystem_bytes": blocks * block_size,
            "label": data[120:136].split(b"\0", 1)[0].decode("utf-8")}


def properties(data):
    result = {}
    for line in data.decode("utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if key in result and result[key] != value:
                raise VerificationError("Conflicting build property: " + key)
            result[key] = value
    return result


def pick(reader, candidates, audit, name):
    selected = next((p for p in candidates if reader.exists(p)), None)
    audit.check(name + ":exists", selected is not None, {"selected": selected, "candidates": candidates})
    return selected


def check_vendor_ueventd(data, audit):
    """Check the actual vendor rules that grant in-process app GPU access."""
    identities = {"root": 0, "system": 1000, "graphics": 1003}

    def aid(token):
        # ueventd resolves these columns with getpwnam/getgrnam, so numeric
        # strings must not be accepted as equivalent Android account names.
        return identities.get(token)

    def matches(rule, path):
        pattern = rule["pattern"]
        # Mirror system/core/init/devices.cpp Permissions::Match for ordinary
        # ueventd rules: no '*' is exact, a sole final '*' is a prefix, and
        # interior wildcards use FNM_PATHNAME unless explicitly disabled.
        wildcard = pattern.find("*")
        if wildcard < 0:
            return pattern == path
        if wildcard == len(pattern) - 1:
            return path.startswith(pattern[:-1])
        # This board uses plain '*' rules. Avoid treating Python's bracket
        # or escape semantics as POSIX fnmatch for any future complex rule.
        if any(character in pattern for character in "\\[]"):
            raise VerificationError("Unsupported vendor ueventd wildcard rule: " + rule["rule"])
        if rule["no_fnm_pathname"]:
            return fnmatch.fnmatchcase(path, pattern)
        components, patterns = path.split("/"), pattern.split("/")
        return len(components) == len(patterns) and all(
            fnmatch.fnmatchcase(value, glob) for value, glob in zip(components, patterns))

    rules = []
    for number, raw in enumerate(data.decode("utf-8").splitlines(), 1):
        fields = raw.split("#", 1)[0].split()
        # This product installs explicit device rules here. Sysfs attributes
        # have a separate syntax; system imports are outside this check.
        if not fields or not fields[0].startswith("/dev/"):
            continue
        if (len(fields) not in (4, 5) or not re.fullmatch(r"0?[0-7]{3}", fields[1])
                or (len(fields) == 5 and fields[4] != "no_fnm_pathname")):
            raise VerificationError("Invalid vendor ueventd device rule at line " + str(number))
        rules.append({"line": number, "rule": raw.strip(), "pattern": fields[0],
                      "mode": format(int(fields[1], 8), "04o"),
                      "owner": fields[2], "group": fields[3],
                      "uid": aid(fields[2]), "gid": aid(fields[3]),
                      "no_fnm_pathname": len(fields) == 5})
    expected = (("/dev/dri/card0", "0666", 0, 1003),
                ("/dev/dri/renderD128", "0666", 0, 1003),
                ("/dev/dma_heap/system", "0444", 1000, 1000))
    audit.data["vendor_ueventd"] = {"path": "/etc/ueventd.rc",
                                      "sha256": hashlib.sha256(data).hexdigest(),
                                      "selected_rules": {}}
    for path, mode, uid, gid in expected:
        # ueventd searches backwards so later device rules override earlier
        # matches. Do not fall back to system defaults if vendor has no rule.
        selected = next((rule for rule in reversed(rules) if matches(rule, path)), None)
        audit.data["vendor_ueventd"]["selected_rules"][path] = selected
        audit.check("vendor-ueventd-app-access:" + path,
                    selected is not None and (selected["mode"], selected["uid"], selected["gid"])
                    == (mode, uid, gid),
                    {"device": path, "selected_rule": selected,
                     "expected": {"mode": mode, "uid": uid, "gid": gid}})


def init_actions(data, source):
    """Read action commands needed by this board and Android's USB rc files."""
    actions, action = [], None
    pending, first_line = "", 0
    for number, raw in enumerate(data.decode("utf-8").splitlines(), 1):
        if not pending:
            first_line = number
        pending += raw
        if pending.endswith("\\"):
            pending = pending[:-1] + " "
            continue
        logical, pending = pending, ""
        try:
            tokens = shlex.split(logical, comments=True, posix=True)
        except ValueError as error:
            raise VerificationError("Cannot parse " + source + ":" + str(first_line)) from error
        if not tokens:
            continue
        if not logical[0].isspace():
            action = None
            if tokens[0] == "on":
                action = {"trigger": " ".join(tokens[1:]), "line": first_line, "commands": []}
                actions.append(action)
        elif action is not None:
            action["commands"].append({"line": first_line, "args": tokens})
    if pending:
        raise VerificationError("Unfinished init line continuation: " + source)
    return actions


def require_init_sequence(actions, trigger, commands, audit, name):
    selected = [action for action in actions if action["trigger"] == trigger]
    actual = [command for action in selected for command in action["commands"]]
    cursor, matched = 0, []
    for expected in commands:
        found = next((index for index in range(cursor, len(actual))
                      if actual[index]["args"] == list(expected)), None)
        if found is None:
            audit.check(name, False, {"trigger": trigger, "missing_command": list(expected),
                                      "actual_actions": selected})
        matched.append(actual[found])
        cursor = found + 1
    audit.check(name, True, {"trigger": trigger, "matched_commands": matched})
    return {"trigger": trigger, "matched_commands": matched}


def check_usb_gadget_init(system, vendor, audit):
    board_path = "/etc/init/hw/init.fireflyrk3288.rc"
    sources = {"vendor": (board_path, vendor.read(board_path))}
    for name, basename in (("root", "init.rc"), ("common_usb", "init.usb.rc"),
                           ("common_configfs", "init.usb.configfs.rc")):
        path = pick(system, ("/system/etc/init/hw/" + basename, "/etc/init/hw/" + basename),
                    audit, "usb-init-source:" + name)
        sources[name] = (path, system.read(path))
    actions = {name: init_actions(data, path) for name, (path, data) in sources.items()}
    report = {"sources": {name: {"path": path, "sha256": hashlib.sha256(data).hexdigest()}
                           for name, (path, data) in sources.items()}, "sequences": {}}
    audit.data["usb_gadget_init"] = report

    imports = []
    for raw in sources["root"][1].decode("utf-8").splitlines():
        fields = shlex.split(raw, comments=True, posix=True)
        if len(fields) == 2 and fields[0] == "import":
            imports.append(fields[1])
    required_imports = ("/system/etc/init/hw/init.usb.rc",
                        "/vendor/etc/init/hw/init.${ro.hardware}.rc",
                        "/system/etc/init/hw/init.usb.configfs.rc")
    audit.check("usb-root-imports-board-and-common", all(path in imports for path in required_imports), imports)
    # Root-file actions are registered before imported-file actions. Its
    # on-init configfs mount therefore precedes this board's on-init mkdirs.
    sequences = report["sequences"]
    sequences["configfs_mount"] = require_init_sequence(actions["root"], "init", (
        ("mount", "configfs", "none", "/config", "nodev", "noexec", "nosuid"),
    ), audit, "usb-root-configfs-mount")
    sequences["controller"] = require_init_sequence(actions["vendor"], "early-init", (
        ("setprop", "sys.usb.controller", "ff580000.usb"),
    ), audit, "usb-board-controller-early-init")
    sequences["gadget_setup"] = require_init_sequence(actions["vendor"], "init", (
        ("mkdir", "/config/usb_gadget/g1", "0770", "root", "root"),
        ("write", "/config/usb_gadget/g1/idVendor", "0x18d1"),
        ("write", "/config/usb_gadget/g1/idProduct", "0x4ee7"),
        ("write", "/config/usb_gadget/g1/bcdUSB", "0x0200"),
        ("write", "/config/usb_gadget/g1/bcdDevice", "0x0100"),
        ("mkdir", "/config/usb_gadget/g1/strings/0x409", "0770", "root", "root"),
        ("write", "/config/usb_gadget/g1/strings/0x409/serialnumber", "${ro.serialno}"),
        ("write", "/config/usb_gadget/g1/strings/0x409/manufacturer", "Firefly"),
        ("write", "/config/usb_gadget/g1/strings/0x409/product", "Firefly-RK3288"),
        ("mkdir", "/config/usb_gadget/g1/functions/ffs.adb"),
        ("mkdir", "/config/usb_gadget/g1/configs/b.1", "0770", "shell", "shell"),
        ("mkdir", "/config/usb_gadget/g1/configs/b.1/strings/0x409", "0770", "shell", "shell"),
        ("write", "/config/usb_gadget/g1/configs/b.1/MaxPower", "500"),
        ("mkdir", "/dev/usb-ffs", "0775", "shell", "shell"),
        ("mkdir", "/dev/usb-ffs/adb", "0770", "shell", "shell"),
        ("mount", "functionfs", "adb", "/dev/usb-ffs/adb",
         "rmode=0770,fmode=0660,uid=2000,gid=2000"),
        ("setprop", "sys.usb.configfs", "1"),
    ), audit, "usb-board-gadget-before-configfs-enable")
    vendor_commands = [(action["trigger"], command) for action in actions["vendor"]
                       for command in action["commands"]]
    configfs = [(trigger, command) for trigger, command in vendor_commands
                if command["args"][:2] == ["setprop", "sys.usb.configfs"]]
    controller = [(trigger, command) for trigger, command in vendor_commands
                  if command["args"][:2] == ["setprop", "sys.usb.controller"]]
    audit.check("usb-board-single-configfs-enable",
                len(configfs) == 1 and configfs[0][0] == "init"
                and configfs[0][1] == sequences["gadget_setup"]["matched_commands"][-1], configfs)
    audit.check("usb-board-single-controller",
                len(controller) == 1 and controller[0][0] == "early-init"
                and controller[0][1]["args"] == ["setprop", "sys.usb.controller", "ff580000.usb"], controller)
    premature = [(trigger, command) for trigger, command in vendor_commands
                 if command["args"][:2] in (["write", "/config/usb_gadget/g1/UDC"], ["start", "adbd"])]
    audit.check("usb-board-defers-adbd-and-udc-to-common", not premature, premature)
    sequences["boot_config"] = require_init_sequence(
        actions["common_usb"], "boot && property:persist.sys.usb.config=*", (
            ("setprop", "sys.usb.config", "${persist.sys.usb.config}"),
        ), audit, "usb-common-boot-config")
    sequences["disable"] = require_init_sequence(
        actions["common_configfs"], "property:sys.usb.config=none && property:sys.usb.configfs=1", (
            ("write", "/config/usb_gadget/g1/UDC", "none"),
            ("stop", "adbd"), ("setprop", "sys.usb.ffs.ready", "0"),
        ), audit, "usb-common-unbind-before-ffs-reset")
    sequences["adbd_start"] = require_init_sequence(
        actions["common_configfs"], "property:sys.usb.config=adb && property:sys.usb.configfs=1", (
            ("start", "adbd"),
        ), audit, "usb-common-adbd-configfs-gate")
    sequences["bind"] = require_init_sequence(
        actions["common_configfs"],
        "property:sys.usb.ffs.ready=1 && property:sys.usb.config=adb && property:sys.usb.configfs=1", (
            ("write", "/config/usb_gadget/g1/configs/b.1/strings/0x409/configuration", "adb"),
            ("symlink", "/config/usb_gadget/g1/functions/ffs.adb", "/config/usb_gadget/g1/configs/b.1/f1"),
            ("write", "/config/usb_gadget/g1/UDC", "${sys.usb.controller}"),
            ("setprop", "sys.usb.state", "${sys.usb.config}"),
        ), audit, "usb-common-ffs-ready-before-udc-bind")


def verify_android(system, vendor, audit):
    audit.stage = "android-system"
    prop_path = pick(system, ("/system/build.prop", "/build.prop"), audit, "system-build-prop")
    # With system-as-root, /system is an actual directory inside this image.
    system.mount_prefix = None if prop_path.startswith("/system/") else "system"
    props = properties(system.read(prop_path))
    for suffix, expected in (("release", "17"), ("sdk", "37")):
        values = {key: props[key] for key in ("ro.build.version." + suffix,
                                            "ro.system.build.version." + suffix) if key in props}
        audit.check("android-version:" + suffix, bool(values) and set(values.values()) == {expected}, values)
    audit.check("authenticated-usb-adb-property", props.get("ro.adb.secure") == "1",
                props.get("ro.adb.secure"))
    init = pick(system, ("/system/bin/init", "/bin/init", "/init"), audit, "system-init")
    real, binary = system.dump(init)
    audit.check("system-init-executable-mode", bool(system.inode(real)["mode"] & 0o111))
    installed_init = "/system" + real if system.mount_prefix == "system" else real
    init_info = elf_info(binary, installed_path=installed_init)
    audit.check("system-init-arm32", True, {"path": real, **init_info})
    if init_info["interpreter"] == "/system/bin/bootstrap/linker":
        linker_path = "/bin/bootstrap/linker" if system.mount_prefix == "system" else "/system/bin/bootstrap/linker"
        linker_real, linker_binary = system.dump(linker_path)
        audit.check("system-init-bootstrap-linker-executable", bool(system.inode(linker_real)["mode"] & 0o111))
        linker_info = elf_info(linker_binary)
        audit.check("system-init-bootstrap-linker-arm32", linker_info["interpreter"] is None,
                    {"path": linker_real, **linker_info})
    audit.data["android"] = {"version": "17", "sdk": 37, "system_build_prop": prop_path, "init": real}

    audit.stage = "android-vendor"
    vendor_prop = pick(vendor, ("/build.prop", "/vendor/build.prop"), audit, "vendor-build-prop")
    vprops = properties(vendor.read(vendor_prop))
    for key, value in (("ro.hardware.egl", "mesa"), ("ro.hardware.gralloc", "minigbm"),
                       ("ro.hardware.hwcomposer", "drm"), ("persist.sys.usb.config", "adb")):
        audit.check("vendor-property:" + key, vprops.get(key) == value, vprops.get(key))
    members = (
        ("egl", ("/lib/egl/libEGL_mesa.so",)),
        ("gles1", ("/lib/egl/libGLESv1_CM_mesa.so",)),
        ("gles2", ("/lib/egl/libGLESv2_mesa.so",)),
        ("panfrost-gallium", ("/lib/libgallium_dri.so", "/lib/dri/libgallium_dri.so")),
        ("minigbm-gralloc", ("/lib/libminigbm_gralloc.so",)),
        ("minigbm-mapper", ("/lib/hw/mapper.minigbm.so", "/lib/mapper.minigbm.so")),
        ("minigbm-allocator", ("/bin/hw/android.hardware.graphics.allocator-service.minigbm",)),
        ("drm-composer", ("/bin/hw/android.hardware.composer.hwc3-service.drm",)),
        ("keymint", ("/bin/hw/android.hardware.security.keymint-service.nonsecure",)),
    )
    audit.data["vendor_elf"] = {}
    for name, candidates in members:
        path = pick(vendor, candidates, audit, "vendor:" + name)
        real, binary = vendor.dump(path)
        info = elf_info(binary)
        audit.check("vendor-arm32:" + name, True, {"path": real, **info})
        audit.data["vendor_elf"][name] = {"path": real, **info}
        if path.startswith("/bin/"):
            audit.check("vendor-service-executable:" + name, bool(vendor.inode(real)["mode"] & 0o111))
        if name == "panfrost-gallium":
            previous, found = b"", False
            with opened(binary) as stream:
                for block in iter(lambda: stream.read(CHUNK), b""):
                    combined = previous + block.lower()
                    if b"panfrost" in combined:
                        found = True
                        break
                    previous = combined[-7:]
            audit.check("gallium-contains-panfrost-driver", found)
    fstab = pick(vendor, ("/etc/fstab.fireflyrk3288",), audit, "vendor-fstab")
    check_fstab(vendor.read(fstab), audit, "vendor-fstab")
    for path in ("/etc/init/hw/init.fireflyrk3288.rc", "/etc/ueventd.rc"):
        audit.check("vendor-board-file:" + path, vendor.exists(path), path)
    check_vendor_ueventd(vendor.read("/etc/ueventd.rc"), audit)
    check_usb_gadget_init(system, vendor, audit)


def verify_system_adbd_apex(system, product, aosp_option, scratch, audit):
    """Verify the CAPEX from the actual system filesystem, never a substitute."""
    audit.stage = "android-adbd-apex"
    product = product.resolve(strict=True)
    if aosp_option is None:
        if len(product.parents) < 4:
            raise VerificationError("Cannot derive AOSP root; pass --aosp explicitly")
        aosp = product.parents[3]
    else:
        aosp = aosp_option.resolve(strict=True)
    expected_product = aosp / "out/target/product/rk3288"
    audit.check("adbd-apex-aosp-product-layout", aosp.is_dir()
                and expected_product.resolve(strict=True) == product,
                {"aosp": str(aosp), "product": str(product),
                 "expected_product": str(expected_product)})
    capex_path = pick(system, ("/system/apex/com.android.adbd.capex",
                               "/apex/com.android.adbd.capex"), audit, "system-adbd-capex")
    actual_path, capex = system.dump(capex_path)
    evidence = {"filesystem_path": actual_path, "bytes": capex.stat().st_size,
                "sha256": digest(capex), "aosp": str(aosp)}
    audit.data["system_adbd_capex"] = evidence
    helper = regular(Path(__file__).absolute().with_name("verify-adbd-apex.py"))
    before = snapshot(helper)
    audit.data["adbd_apex_helper"] = {"path": str(helper), "sha256": digest(helper)}
    spec = importlib.util.spec_from_file_location("firefly_verify_adbd_apex", helper)
    if spec is None or spec.loader is None:
        raise VerificationError("Cannot load ADB APEX verification helper: " + str(helper))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        result = module.verify_adbd_apex(aosp, capex, scratch)
    except Exception as error:
        partial = getattr(error, "report", None)
        audit.data["adbd_apex"] = partial if isinstance(partial, dict) else {}
        audit.data["adbd_apex"]["error"] = {"type": type(error).__name__, "message": str(error)}
        audit.check("actual-system-adbd-apex-build-and-patch", False,
                    {"system_capex": evidence, "error": str(error)})
    audit.data["adbd_apex"] = result
    audit.check("actual-system-adbd-apex-build-and-patch",
                isinstance(result, dict) and result.get("passed") is True,
                {"system_capex": evidence, "helper_passed": result.get("passed")
                 if isinstance(result, dict) else None})
    audit.check("adbd-apex-helper-unchanged-during-verification", snapshot(helper) == before)
    return aosp


def bind_graphics_inputs_to_image(result, filesystems, audit, expected_roots=None):
    """Match the helper's staged-file inputs to actual packaged file content."""
    inputs, apex_dependencies = {}, {}
    report = {"scope": "Packaged file hashes for installed-product graphics ELF audit inputs",
              "namespace_topology_source": "installed product staging directories",
              "image_namespace_topology_verified": False, "files": [], "apex_dependencies": []}
    audit.data["graphics_elf_image_binding"] = report
    if expected_roots is None:
        expected_roots = {
            "/vendor/lib/egl/libEGL_mesa.so", "/vendor/lib/egl/libGLESv1_CM_mesa.so",
            "/vendor/lib/egl/libGLESv2_mesa.so", "/vendor/lib/libgallium_dri.so",
            "/vendor/lib/libminigbm_gralloc.so",
            "/vendor/lib/hw/mapper.minigbm.so",
            "/vendor/bin/hw/android.hardware.graphics.allocator-service.minigbm",
            "/vendor/bin/hw/android.hardware.composer.hwc3-service.drm",
        }
    roots = result.get("roots", [])
    audit.check("graphics-helper-complete-root-set", len(roots) == len(expected_roots)
                and {root.get("root") for root in roots} == expected_roots,
                [root.get("root") for root in roots])

    def add_input(path, expected, role):
        if not isinstance(path, str) or not path.startswith("/") or any(
                part in ("", ".", "..") for part in path[1:].split("/")):
            raise VerificationError("Invalid graphics helper file path: " + str(path))
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            raise VerificationError("Invalid graphics helper SHA-256: " + path)
        if path.startswith("/apex/"):
            previous = apex_dependencies.get(path)
            if previous is not None and previous != expected:
                raise VerificationError("Conflicting APEX dependency hashes: " + path)
            apex_dependencies[path] = expected
            return
        if path in inputs and inputs[path]["sha256"] != expected:
            raise VerificationError("Conflicting graphics input hashes: " + path)
        inputs.setdefault(path, {"sha256": expected, "roles": set()})["roles"].add(role)

    for root in roots:
        dependencies = root.get("dependencies", [])
        audit.check("graphics-helper-root-evidence:" + root.get("name", "unknown"),
                    root.get("passed") is True and bool(dependencies), root.get("root"))
        canonical = root.get("canonical_root", dependencies[0]["path"])
        root_dependency = next((entry for entry in dependencies if entry["path"] == canonical), None)
        audit.check("graphics-helper-root-hash:" + root["name"], root_dependency is not None, canonical)
        add_input(root["root"], root_dependency["sha256"], "graphics-root")
        for dependency in dependencies:
            add_input(dependency["path"], dependency["sha256"], "ELF-dependency")
    linkers = result.get("runtime_linkers")
    if linkers is None:
        linkers = {"arm": result.get("runtime_linker")}
    audit.check("graphics-helper-runtime-linker-evidence", isinstance(linkers, dict) and bool(linkers)
                and all(isinstance(linker, dict) for linker in linkers.values()), linkers)
    for linker in linkers.values():
        add_input(linker["path"], linker["sha256"], "runtime-linker")
    for path, info in result.get("namespace_input_files", {}).items():
        add_input("/" + path, info["sha256"], "namespace-input")
    packages = {}
    for package in result.get("apex_packages", []):
        name = package["name"]
        if name in packages:
            raise VerificationError("Duplicate graphics helper APEX name: " + name)
        packages[name] = package
        add_input("/" + package["archive"], package["sha256"], "APEX-archive")
    # All ELF and namespace inputs outside APEX are exported from the actual
    # partition payloads. Staging directories alone cannot establish this.
    for path, expected in sorted(inputs.items()):
        partition, relative = path[1:].split("/", 1)
        audit.check("graphics-input-partition-present:" + path, partition in filesystems, partition)
        filesystem = filesystems[partition]
        member = "/" + relative
        if partition == "system" and filesystem.mount_prefix is None:
            member = "/system" + member
        real, exported = filesystem.dump(member)
        actual = digest(exported)
        detail = {"path": path, "partition": partition, "filesystem_path": real,
                  "bytes": exported.stat().st_size, "sha256": actual,
                  "expected_sha256": expected["sha256"], "roles": sorted(expected["roles"])}
        report["files"].append(detail)
        audit.check("graphics-input-packaged-content:" + path, actual == expected["sha256"], detail)
        exported.unlink()
    # APEX dependencies were extracted by the helper from these same complete
    # archives. Matching each archive binds the extracted bytes to the image.
    for path, expected in sorted(apex_dependencies.items()):
        name = path.split("/", 3)[2]
        package = packages.get(name)
        audit.check("graphics-apex-dependency-packaged:" + path, package is not None,
                    {"path": path, "sha256": expected, "apex": name})
        report["apex_dependencies"].append({"path": path, "sha256": expected,
                                              "archive": package["archive"],
                                              "archive_sha256": package["sha256"]})
    report.update(passed=True, packaged_regular_files=len(inputs),
                  apex_dependency_files=len(apex_dependencies))


def verify_graphics_product(product, aosp, scratch, filesystems, audit):
    audit.stage = "android-graphics-elf"
    helper = regular(Path(__file__).absolute().with_name("verify-graphics-elf.py"))
    before = snapshot(helper)
    audit.data["graphics_elf_helper"] = {"path": str(helper), "sha256": digest(helper)}
    spec = importlib.util.spec_from_file_location("firefly_verify_graphics_elf", helper)
    if spec is None or spec.loader is None:
        raise VerificationError("Cannot load graphics ELF verification helper: " + str(helper))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    graphics_scratch = scratch / "graphics-elf"
    graphics_scratch.mkdir()
    try:
        result = module.verify_graphics_elf(product, aosp, graphics_scratch)
    except Exception as error:
        partial = getattr(error, "report", None)
        audit.data["graphics_elf"] = partial if isinstance(partial, dict) else {}
        audit.data["graphics_elf"]["error"] = {"type": type(error).__name__, "message": str(error)}
        audit.check("installed-product-graphics-elf-closure", False, str(error))
    audit.data["graphics_elf"] = result
    audit.check("installed-product-graphics-elf-closure",
                isinstance(result, dict) and result.get("passed") is True
                and result.get("graphics_verified") is True,
                {"scope": result.get("scope") if isinstance(result, dict) else None})
    bind_graphics_inputs_to_image(result, filesystems, audit)
    audit.check("graphics-elf-helper-unchanged-during-verification", snapshot(helper) == before)


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def source_manifest_hash(source, manifest, audit):
    matches = [(key, value) for key, value in manifest["inputs"].items()
               if Path(key).name == source.name]
    audit.check("input-record:" + source.name, len(matches) == 1,
                [key for key, _ in matches])
    actual = digest(source)
    audit.check("original-input-sha256:" + source.name, actual == matches[0][1],
                {"source": str(source), "sha256": actual, "recorded": matches[0][1]})
    return actual


def raw_source(source, scratch, simg2img, audit):
    if read_at(source, 0, 4) != b"\x3a\xff\x26\xed":
        return source
    if simg2img is None:
        location = shutil.which("simg2img")
        if location is None:
            raise VerificationError("Sparse AOSP input requires --simg2img")
        simg2img = regular(Path(location))
    dest = scratch / (source.stem + "-aosp-raw.img")
    audit.run("expand-original-sparse:" + source.name, simg2img, source, dest)
    return regular(dest)


def verify(a, audit, scratch):
    boot_medium = getattr(a, "boot_medium", "sd")
    image = regular(a.image)
    if a.image.is_symlink():
        raise VerificationError("Image must be an ordinary file, not a symlink")
    manifest_path = regular(a.manifest or a.image.with_suffix(a.image.suffix + ".json"))
    manifest = json.loads(manifest_path.read_text(), object_pairs_hook=unique_json)
    audit.data.update(image=str(image), manifest=str(manifest_path), boot_medium=boot_medium,
                      boot_device=BOOT_MEDIA[boot_medium]["device"])
    audit.check("image-size", image.stat().st_size == DISK_BYTES, image.stat().st_size)
    audit.check("manifest-schema", manifest.get("format") == 1
                and manifest.get("image_size") == DISK_BYTES
                and isinstance(manifest.get("inputs"), dict)
                and isinstance(manifest.get("partitions"), list)
                and len(manifest["partitions"]) == 7
                and isinstance(manifest.get("image_sha256"), str)
                and SHA256.fullmatch(manifest["image_sha256"]) is not None)
    audit.check("manifest-input-hash-format", all(isinstance(k, str) and isinstance(v, str)
                and SHA256.fullmatch(v) for k, v in manifest["inputs"].items()))
    audit.check("manifest-boot-medium", manifest.get("boot_medium", "sd") == boot_medium
                and manifest.get("boot_device", BOOT_MEDIA[boot_medium]["device"]) == BOOT_MEDIA[boot_medium]["device"],
                {"requested": boot_medium, "recorded": manifest.get("boot_medium", "sd")})
    idb, uboot = regular(a.idbloader), regular(a.uboot)
    source_inputs = [idb, uboot]
    source_inputs.extend(regular(a.product / (name + ".img")) for name in
                         ("system", "system_ext", "product", "vendor", "userdata"))
    source_inputs.extend(regular(a.boot_files / name) for name in
                         ("boot/zImage", "boot/ramdisk.img", "boot/rk3288-firefly-android.dtb",
                          "extlinux/extlinux.conf"))
    if a.simg2img is not None:
        source_inputs.append(regular(a.simg2img))
    observations = {path: snapshot(path) for path in [image, manifest_path, *source_inputs]}
    input_hashes = {path: source_manifest_hash(path, manifest, audit) for path in source_inputs}
    partitions = parse_gpt(image, audit)
    verify_loaders(image, idb, uboot, audit, boot_medium, scratch)
    records = {part.get("name"): part for part in manifest["partitions"]}
    audit.check("manifest-partition-name-set", set(records) == {name for name, _, _ in EXPECTED})
    extracted = {}
    audit.data["filesystems"] = {}
    for part in partitions:
        audit.stage = "partition:" + part["name"]
        name = part["name"]
        record = records[name]
        audit.check("manifest-layout:" + name,
                    all(record.get(key) == part[key] for key in ("offset", "size", "uuid")))
        length, expected_hash = record.get("filesystem_image_bytes"), record.get("filesystem_sha256")
        audit.check("manifest-payload-bounds:" + name, type(length) is int and 0 < length <= part["size"]
                    and isinstance(expected_hash, str) and SHA256.fullmatch(expected_hash) is not None,
                    {"payload_bytes": length, "capacity": part["size"]})
        payload = scratch / (name + "-partition.img")
        actual_hash = extract_region(image, payload, part["offset"], length)
        audit.check("payload-sha256:" + name, actual_hash == expected_hash,
                    {"bytes": length, "sha256": actual_hash, "recorded": expected_hash})
        audit.check("partition-tail-zero:" + name,
                    zero_region(image, part["offset"] + length, part["size"] - length),
                    part["size"] - length)
        extracted[name] = payload
        if name == "boot":
            verify_fat(payload, a.boot_files, scratch, audit, uboot, boot_medium)
            continue
        info = superblock(payload)
        audit.check("ext4-size:" + name, 0 < info["filesystem_bytes"] <= length, info)
        audit.run("ext4-readonly-e2fsck:" + name, "e2fsck", "-f", "-n", payload)
        audit.data["filesystems"][name] = info
        if name == "metadata":
            audit.check("metadata-label", info["label"] == "metadata", info["label"])
            tree = Ext4(payload, scratch, "metadata").inventory()
            audit.check("metadata-initially-empty", set(tree) <= {"/", "/lost+found"}
                        and all(item["type"] == "directory" for item in tree.values()), sorted(tree))
        else:
            source = regular(a.product / (name + ".img"))
            raw = raw_source(source, scratch, a.simg2img, audit)
            if name != "userdata":
                raw_hash = input_hashes[source] if raw == source else digest(raw)
                audit.check("aosp-raw-payload-identical:" + name,
                            raw.stat().st_size == length and raw_hash == actual_hash,
                            {"source": str(source), "raw_bytes": raw.stat().st_size,
                             "raw_sha256": raw_hash, "payload_sha256": actual_hash})
            else:
                source_info = superblock(raw)
                audit.check("userdata-source-fits", raw.stat().st_size <= length,
                            {"source_bytes": raw.stat().st_size, "expanded_bytes": length})
                audit.check("userdata-uuid-preserved", source_info["uuid"] == info["uuid"],
                            {"source": source_info["uuid"], "expanded": info["uuid"]})
                audit.check("userdata-expanded-to-partition", length == part["size"]
                            and info["filesystem_bytes"] == part["size"], info)
                original = Ext4(raw, scratch, "data").inventory()
                expanded = Ext4(payload, scratch, "data").inventory()
                changes = [key for key in sorted(original.keys() | expanded.keys())
                           if original.get(key) != expanded.get(key)]
                audit.check("userdata-initial-tree-and-content-preserved", not changes,
                            {"source_entries": len(original), "expanded_entries": len(expanded),
                             "changed_paths": changes[:100]})
    filesystems = {name: Ext4(extracted[name], scratch, None if name == "system" else name)
                   for name in ("system", "system_ext", "product", "vendor")}
    system_fs = filesystems["system"]
    verify_android(system_fs, filesystems["vendor"], audit)
    aosp_root = verify_system_adbd_apex(system_fs, a.product, a.aosp, scratch, audit)
    verify_graphics_product(a.product, aosp_root, scratch, filesystems, audit)
    audit.stage = "delivery"
    actual = digest(image)
    audit.check("whole-image-sha256", actual == manifest["image_sha256"],
                {"sha256": actual, "recorded": manifest["image_sha256"]})
    changed = [str(path) for path, before in observations.items() if snapshot(path) != before]
    audit.check("image-and-inputs-unchanged-during-verification", not changed, changed)
    audit.data.update(image_sha256=actual, image_verified=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--boot-medium", choices=("sd", "emmc"), default="sd",
                        help="Expected boot contract; default sd preserves TF-card verification")
    parser.add_argument("--check-tools", action="store_true", help="Only check tool availability; do not verify an image")
    parser.add_argument("--image", type=Path, help="Completed ordinary raw .img file")
    parser.add_argument("--product", type=Path, help="The actual AOSP product output directory")
    parser.add_argument("--aosp", type=Path,
                        help="AOSP root for ADB APEX and graphics ELF evidence; default: PRODUCT's fourth parent")
    parser.add_argument("--boot-files", type=Path, help="The actual boot/ and extlinux/ source directory")
    parser.add_argument("--idbloader", type=Path)
    parser.add_argument("--uboot", type=Path)
    parser.add_argument("--simg2img", type=Path, help="AOSP simg2img, needed only for sparse AOSP inputs")
    parser.add_argument("--manifest", type=Path, help="Default: IMAGE.img.json sidecar")
    parser.add_argument("--report", type=Path, required=True, help="New JSON report; existing files are never overwritten")
    parser.add_argument("--scratch-dir", type=Path, help="Parent for private temporary partition copies (up to about 20 GiB)")
    args = parser.parse_args()
    if not args.check_tools:
        for name in ("image", "product", "boot_files", "idbloader", "uboot"):
            if getattr(args, name) is None:
                parser.error("--" + name.replace("_", "-") + " is required for image verification")
    report = args.report.absolute()
    if str(report).startswith("/dev/") or report.exists() or report.is_symlink():
        parser.error("--report must be a new ordinary file outside /dev")
    # O_EXCL also protects the image/build inputs if mistakenly supplied as the report.
    try:
        descriptor = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    except OSError as error:
        parser.error("Cannot create report: " + str(error))
    audit = Audit("tool-preflight-only" if args.check_tools else "raw-image-and-actual-build-inputs")
    success = False
    try:
        preflight(audit)
        if args.check_tools:
            audit.finish("tools-ready")
        else:
            parent = args.scratch_dir or args.image.absolute().parent
            if not parent.is_dir():
                raise VerificationError("Scratch parent directory does not exist: " + str(parent))
            if args.simg2img is not None:
                args.simg2img = regular(args.simg2img)
            with tempfile.TemporaryDirectory(prefix="firefly-verify-", dir=parent) as temporary:
                verify(args, audit, Path(temporary))
            audit.finish("passed")
        success = True
    except Exception as error:
        audit.data["image_verified"] = False
        audit.data["error"] = {"type": type(error).__name__, "message": str(error)}
        if not isinstance(error, VerificationError):
            audit.data["checks"].append({"stage": audit.stage, "name": "execution",
                                          "passed": False, "detail": str(error)})
        elif not audit.data["checks"] or audit.data["checks"][-1]["passed"]:
            audit.data["checks"].append({"stage": audit.stage, "name": "validation",
                                          "passed": False, "detail": str(error)})
        audit.finish("failed")
        print("Verification failed: " + str(error), file=sys.stderr)
    finally:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(audit.data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    print(json.dumps({"result": audit.data["result"], "image_verified": audit.data["image_verified"],
                      "checks_executed": audit.data["checks_executed"], "report": str(report)}))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
