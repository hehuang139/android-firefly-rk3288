#!/usr/bin/env python3
"""Assemble an SD/eMMC image from actual AOSP partitions and board boot files.

Never opens block devices. Android sparse input is expanded by AOSP simg2img.
"""
# SPDX-License-Identifier: MIT
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import uuid
import zlib

SECTOR = 512
MIB = 1024 * 1024
TOTAL = 12 * 1024 * MIB
LINUX_FS = "0fc63daf-8483-4772-8e79-3d69d8477de4"
BASIC_DATA = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"
LAYOUT = [("boot", 256), ("system", 4096), ("system_ext", 1024),
          ("product", 1024), ("vendor", 512), ("metadata", 32),
          ("userdata", None)]
BOOT_MEDIA = {
    "sd": {"device": "ff0c0000.mmc", "emmc_status": "disabled", "sd_status": "okay",
           "bootcmd": "setenv boot_targets mmc1; bootflow scan -lb"},
    "emmc": {"device": "ff0f0000.mmc", "emmc_status": "okay", "sd_status": "disabled",
             "bootcmd": "mmc dev 0 && mmc rescan && sysboot mmc 0:1 any ${scriptaddr} /extlinux/extlinux.conf"},
}


def run(*cmd):
    subprocess.run([str(x) for x in cmd], check=True)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * MIB), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_at(out, src, offset, capacity):
    size = src.stat().st_size
    if size > capacity:
        raise ValueError(f"{src} is {size} bytes, exceeds capacity {capacity}")
    out.seek(offset)
    zero = b"\0" * (4 * MIB)
    with src.open("rb") as f:
        while data := f.read(len(zero)):
            if data == zero[:len(data)]:
                out.seek(len(data), os.SEEK_CUR)
            else:
                out.write(data)


def gpt(out, partitions, disk_uuid):
    sectors = TOTAL // SECTOR
    entries = bytearray(128 * 128)
    for index, part in enumerate(partitions):
        name = part["name"].encode("utf-16-le")
        ident = uuid.uuid5(disk_uuid, part["name"])
        part["uuid"] = str(ident)
        part_type = BASIC_DATA if part["name"] == "boot" else LINUX_FS
        entry = struct.pack("<16s16sQQQ72s", uuid.UUID(part_type).bytes_le,
                            ident.bytes_le, part["offset"] // SECTOR,
                            (part["offset"] + part["size"]) // SECTOR - 1, 0, name)
        entries[index * 128:(index + 1) * 128] = entry
    entries_crc = zlib.crc32(entries)

    def header(current, backup, table):
        values = [b"EFI PART", 0x10000, 92, 0, 0, current, backup, 34,
                  sectors - 34, disk_uuid.bytes_le, table, 128, 128, entries_crc]
        h = struct.pack("<8sIIIIQQQQ16sQIII", *values)
        values[3] = zlib.crc32(h)
        return struct.pack("<8sIIIIQQQQ16sQIII", *values).ljust(SECTOR, b"\0")

    mbr = bytearray(SECTOR)
    mbr[446:462] = struct.pack("<B3sB3sII", 0, b"\0\2\0", 0xEE,
                                b"\xff\xff\xff", 1, sectors - 1)
    mbr[510:512] = b"\x55\xaa"
    for offset, data in [(0, mbr), (SECTOR, header(1, sectors - 1, 2)),
                         (2 * SECTOR, entries),
                         ((sectors - 33) * SECTOR, entries),
                         ((sectors - 1) * SECTOR, header(sectors - 1, 1, sectors - 33))]:
        out.seek(offset)
        out.write(data)


def raw_image(src, scratch, simg2img):
    with src.open("rb") as f:
        sparse = f.read(4) == b"\x3a\xff\x26\xed"
    if not sparse:
        return src
    dest = scratch / (src.stem + ".raw.img")
    run(simg2img, src, dest)
    return dest


def check_boot_medium_files(boot_files, boot_medium="sd"):
    medium = BOOT_MEDIA[boot_medium]
    dtb = boot_files / "boot/rk3288-firefly-android.dtb"
    properties = (("/", "compatible", "firefly,firefly-rk3288"),
                  ("/mmc@ff0f0000", "status", medium["emmc_status"]),
                  ("/mmc@ff0c0000", "status", medium["sd_status"]))
    for node, name, expected in properties:
        values = subprocess.check_output(["fdtget", "-t", "s", str(dtb), node, name], text=True).split()
        if expected not in values:
            raise ValueError(f"{boot_medium} DTB requires {node}:{name}={expected}; found {values}")
    if boot_medium == "emmc":
        frequency = subprocess.check_output(["fdtget", "-t", "u", str(dtb), "/mmc@ff0f0000", "max-frequency"], text=True).split()
        if frequency != ["50000000"]:
            raise ValueError(f"eMMC DTB requires max-frequency=50000000; found {frequency}")
    config = (boot_files / "extlinux/extlinux.conf").read_text()
    directives = {}
    for line in config.splitlines():
        fields = line.split("#", 1)[0].strip().split(None, 1)
        if len(fields) == 2:
            directives.setdefault(fields[0].upper(), []).append(fields[1].strip())
    for key, expected in (("LINUX", "/boot/zImage"), ("INITRD", "/boot/ramdisk.img"),
                          ("FDT", "/boot/rk3288-firefly-android.dtb")):
        if directives.get(key) != [expected]:
            raise ValueError(f"extlinux must select one {key} {expected}")
    append = directives.get("APPEND", [])
    if len(append) != 1:
        raise ValueError("extlinux must have one Android APPEND command line")
    tokens = append[0].split()
    if tokens.count("androidboot.hardware=fireflyrk3288") != 1 or [token for token in tokens if token.startswith("androidboot.boot_devices=")] != ["androidboot.boot_devices=" + medium["device"]]:
        raise ValueError(f"extlinux does not select the {boot_medium} boot device {medium['device']}")


def check_boot_medium_loaders(idbloader, uboot, boot_medium="sd"):
    binary = uboot.read_bytes()
    matches = re.findall(rb"(?:^|\x00)bootcmd=([^\x00]+)\x00", binary)
    if matches != [BOOT_MEDIA[boot_medium]["bootcmd"].encode()]:
        raise ValueError(f"U-Boot bootcmd does not select {boot_medium}: {matches}")
    if boot_medium != "emmc":
        return
    # The independent eMMC SPL must fetch the second loader from eMMC too.
    # Inspect its actual embedded FDT, rather than trusting the input filename.
    binary = idbloader.read_bytes()
    orders = []
    with tempfile.TemporaryDirectory(prefix="firefly-spl-contract-") as temporary:
        offset = 0
        while (offset := binary.find(b"\xd0\x0d\xfe\xed", offset)) >= 0:
            position = offset
            offset += 4
            if position + 40 > len(binary):
                continue
            header = struct.unpack_from(">10I", binary, position)
            _, length, structs, strings, reserve, version, compatible, _, string_size, struct_size = header
            if not (40 <= length <= len(binary) - position and version == 17 and compatible <= 17
                    and 40 <= structs <= length and 40 <= strings <= length and 40 <= reserve < length
                    and structs + struct_size <= length and strings + string_size <= length):
                continue
            path = Path(temporary) / (str(position) + ".dtb")
            path.write_bytes(binary[position:position + length])
            result = subprocess.run(["fdtget", "-t", "s", str(path), "/chosen", "u-boot,spl-boot-order"], capture_output=True, text=True)
            if result.returncode == 0:
                orders.append(result.stdout.split())
    if orders != [["/mmc@ff0f0000"]]:
        raise ValueError(f"eMMC idbloader SPL boot order must be eMMC only; found {orders}")


def check_boot_files(boot_files, boot_medium="sd"):
    check_boot_medium_files(boot_files, boot_medium)
    kernel = (boot_files / "boot/zImage").read_bytes()
    if kernel[36:40] != b"\x18\x28\x6f\x01":
        raise ValueError("Boot kernel is not an ARM zImage")
    raw = gzip.decompress((boot_files / "boot/ramdisk.img").read_bytes())
    position = 0
    entries = {}
    while position + 110 <= len(raw):
        if raw[position:position + 6] not in (b"070701", b"070702"):
            raise ValueError("Android ramdisk is not a newc cpio archive")
        fields = [int(raw[position + 6 + i * 8:position + 14 + i * 8], 16)
                  for i in range(13)]
        size, namesize = fields[6], fields[11]
        name_end = position + 110 + namesize
        if not namesize or name_end > len(raw) or raw[name_end - 1] != 0:
            raise ValueError("Truncated cpio archive filename")
        name = raw[position + 110:name_end - 1].decode("utf-8").removeprefix("./").lstrip("/")
        start = (name_end + 3) & ~3
        if start + size > len(raw):
            raise ValueError("Truncated cpio archive data")
        entries[name] = (fields[1], raw[start:start + size])
        position = (start + size + 3) & ~3
        if name == "TRAILER!!!":
            break
    mode, init = entries.get("init", (0, b""))
    if not stat.S_ISREG(mode) or not mode & 0o111 or init[:5] != b"\x7fELF\x01" or init[18:20] != b"\x28\x00":
        raise ValueError("Ramdisk /init is not an executable ARM32 ELF first-stage init")
    fstab = entries.get("fstab.fireflyrk3288", (0, b""))[1].decode("utf-8")
    for name in ("system", "system_ext", "product", "vendor"):
        if f"/dev/block/by-name/{name} " not in fstab:
            raise ValueError(f"Ramdisk fstab has no {name} partition")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--boot-medium", choices=("sd", "emmc"), default="sd",
                   help="Boot contract; default sd preserves the TF-card image")
    p.add_argument("--product", required=True, type=Path,
                   help="AOSP out/target/product/rk3288")
    p.add_argument("--boot-files", required=True, type=Path,
                   help="Directory containing boot/ and extlinux/ for FAT")
    p.add_argument("--idbloader", required=True, type=Path)
    p.add_argument("--uboot", required=True, type=Path)
    p.add_argument("--simg2img", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    output = a.output.absolute()
    partial = output.with_name(output.name + ".partial")
    # O_EXCL and file-only output prevent accidental device writes/overwrites.
    if str(output).startswith("/dev/") or output.exists() or output.is_symlink():
        p.error("Output must be a new ordinary file outside /dev")
    if partial.exists() or partial.is_symlink():
        p.error(f"Partial output already exists: {partial}")
    required = [a.idbloader, a.uboot, a.simg2img]
    required += [a.product / f"{n}.img" for n, _ in LAYOUT
                 if n not in ("boot", "metadata")]
    required += [a.boot_files / n for n in (
        "boot/zImage", "boot/ramdisk.img", "boot/rk3288-firefly-android.dtb",
        "extlinux/extlinux.conf")]
    for source in required:
        if not source.is_file() or not stat.S_ISREG(source.stat().st_mode):
            p.error(f"Missing ordinary input file: {source}")
    for tool in ("fdtget", "mkfs.vfat", "mcopy", "e2fsck", "mke2fs", "resize2fs"):
        if not shutil.which(tool):
            p.error(f"Required filesystem/DTB tool is missing: {tool}")
    check_boot_files(a.boot_files, a.boot_medium)
    check_boot_medium_loaders(a.idbloader, a.uboot, a.boot_medium)
    output.parent.mkdir(parents=True, exist_ok=True)
    partitions = []
    offset = 16 * MIB
    for name, size in LAYOUT:
        length = size * MIB if size else TOTAL - MIB - offset
        partitions.append(dict(name=name, offset=offset, size=length))
        offset += length
    result = dict(format=1, boot_medium=a.boot_medium, boot_device=BOOT_MEDIA[a.boot_medium]["device"],
                  image_size=TOTAL, partitions=partitions, inputs={})
    with tempfile.TemporaryDirectory(prefix="android-image-", dir=output.parent) as temp:
        scratch = Path(temp)
        fat = scratch / "boot.fat"
        with fat.open("xb") as f:
            f.truncate(256 * MIB)
        run("mkfs.vfat", "-F", "32", "-n", "FIREFLYBOOT", fat)
        for item in sorted(a.boot_files.iterdir()):
            run("mcopy", "-s", "-i", fat, item, "::/")
        files = {"boot": fat}
        for name, _ in LAYOUT:
            if name != "boot":
                if name == "metadata":
                    # Android creates its metadata contents on first boot.
                    files[name] = scratch / "metadata.ext4"
                    with files[name].open("xb") as f:
                        f.truncate(32 * MIB)
                    run("mke2fs", "-t", "ext4", "-F", "-L", "metadata", files[name])
                else:
                    files[name] = raw_image(a.product / f"{name}.img", scratch, a.simg2img)
                run("e2fsck", "-fn", files[name])
                if name == "userdata":
                    # Leave the AOSP output untouched; grow only our copy.
                    grown = scratch / "userdata.expanded.ext4"
                    run("cp", "--sparse=always", files[name], grown)
                    length = next(p["size"] for p in partitions if p["name"] == name)
                    with grown.open("r+b") as f:
                        f.truncate(length)
                    run("resize2fs", grown)
                    run("e2fsck", "-fn", grown)
                    files[name] = grown
        with partial.open("xb") as out:
            out.truncate(TOTAL)
            gpt(out, partitions, uuid.uuid4())
            copy_at(out, a.idbloader, 32 * 1024, 8 * MIB - 32 * 1024)
            copy_at(out, a.uboot, 8 * MIB, 8 * MIB)
            for part in partitions:
                src = files[part["name"]]
                copy_at(out, src, part["offset"], part["size"])
                part["filesystem_image_bytes"] = src.stat().st_size
                part["filesystem_sha256"] = digest(src)
            out.flush()
            os.fsync(out.fileno())
        for source in required:
            result["inputs"][str(source)] = digest(source)
    result["image_sha256"] = digest(partial)
    # Publish a final filename only after assembly, input checks, fsck and hash
    # have completed. link() also refuses concurrent output creation.
    os.link(partial, output)
    partial.unlink()
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(result, indent=2) + "\n")
    print(f"Assembled image: {output}")


if __name__ == "__main__":
    main()
