#!/usr/bin/env python3
"""Assemble a new RK3399 eMMC raw image from actual ARM64 partitions and verified loaders.

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
BOOT_MEDIA = {"emmc": {"device": "fe330000.mmc"}}



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


def check_boot_medium_files(boot_files, boot_medium="emmc"):
    dtb = boot_files / "boot/rk3399-firefly-android.dtb"
    for node, name, expected in (("/", "compatible", "firefly,firefly-rk3399"),
                                 ("/mmc@fe330000", "status", "okay")):
        values = subprocess.check_output(["fdtget", "-t", "s", str(dtb), node, name], text=True).split()
        if expected not in values:
            raise ValueError(f"RK3399 DTB requires {node}:{name}={expected}; found {values}")
    directives = {}
    for line in (boot_files / "extlinux/extlinux.conf").read_text().splitlines():
        fields = line.split("#", 1)[0].strip().split(None, 1)
        if len(fields) == 2:
            directives.setdefault(fields[0].upper(), []).append(fields[1].strip())
    for key, expected in (("LINUX", "/boot/Image"), ("INITRD", "/boot/ramdisk.img"),
                          ("FDT", "/boot/rk3399-firefly-android.dtb")):
        if directives.get(key) != [expected]:
            raise ValueError(f"extlinux must select exactly {key} {expected}")
    lines = directives.get("APPEND", [])
    if len(lines) != 1:
        raise ValueError("Exactly one Android APPEND is required")
    tokens = lines[0].split()
    for key, expected in (("androidboot.hardware", "fireflyrk3399"),
                          ("androidboot.boot_devices", "fe330000.mmc")):
        if [token for token in tokens if token.startswith(key + "=")] != [key + "=" + expected]:
            raise ValueError("Incorrect board or boot device in extlinux: " + key)


def check_boot_medium_loaders(idbloader, uboot, manifest, boot_files):
    record = json.loads(manifest.read_text())
    if (record.get("status") != "OFFLINE_BUILD_VALIDATED_NOT_BOOTED"
            or record.get("board") != "original Firefly-RK3399 DDR3"
            or record.get("spl_boot_order") != "/mmc@fe330000 only"
            or record.get("environment") != "nowhere"):
        raise ValueError("Missing matching RK3399 eMMC bootloader validation")
    for path, name in ((idbloader, "idbloader.img"), (uboot, "u-boot.itb")):
        entry = record["assets"][name]
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError("Loader differs from validated build: " + name)
    if uboot.read_bytes()[:4] != bytes.fromhex("d00dfeed"):
        raise ValueError("ARM64 U-Boot must be a FIT image")
    env = record["default_environment"]
    if env["boot_targets"] != "mmc0" or env.get("bootcmd") != "bootflow scan -lbG mmc0":
        raise ValueError("U-Boot must restrict initial boot to eMMC")
    load = {key: int(env[key], 16) for key in ("kernel_addr_r", "fdt_addr_r", "ramdisk_addr_r")}
    kernel = boot_files / "boot/Image"
    with kernel.open("rb") as stream:
        header = stream.read(64)
    if len(header) != 64 or header[56:60] != b"ARM\x64":
        raise ValueError("Invalid ARM64 Image header")
    memory_bytes = struct.unpack_from("<Q", header, 16)[0]
    text_offset = struct.unpack_from("<Q", header, 8)[0]
    image_flags = struct.unpack_from("<Q", header, 24)[0]
    if not memory_bytes:
        raise ValueError("ARM64 Image must declare its memory footprint")
    if text_offset != 0 or not image_flags & 8 or (load["kernel_addr_r"] - text_offset) % 0x200000:
        raise ValueError("Kernel load address does not match booti's aligned ARM64 placement")
    windows = [(load["kernel_addr_r"], max(memory_bytes, kernel.stat().st_size)),
               (load["fdt_addr_r"], (boot_files / "boot/rk3399-firefly-android.dtb").stat().st_size),
               (load["ramdisk_addr_r"], (boot_files / "boot/ramdisk.img").stat().st_size)]
    for i, (start, size) in enumerate(windows):
        if start + size >= 0xf8000000:
            raise ValueError("Boot payload extends into SoC address space")
        for other, other_size in windows[:i]:
            if start < other + other_size and other < start + size:
                raise ValueError("U-Boot load addresses overlap")


def check_boot_files(boot_files, boot_medium="emmc"):
    check_boot_medium_files(boot_files, boot_medium)
    kernel = (boot_files / "boot/Image").read_bytes()
    if kernel[56:60] != b"ARM\x64":
        raise ValueError("Boot kernel is not an ARM64 Image")
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
    if not stat.S_ISREG(mode) or not mode & 0o111 or init[:5] != b"\x7fELF\x02" or init[18:20] != b"\xb7\x00":
        raise ValueError("Ramdisk /init is not an executable AArch64 ELF first-stage init")
    fstab = entries.get("fstab.fireflyrk3399", (0, b""))[1].decode("utf-8")
    for name in ("system", "system_ext", "product", "vendor"):
        if f"/dev/block/by-name/{name} " not in fstab:
            raise ValueError(f"Ramdisk fstab has no {name} partition")


def check_kernel_manifest(boot_files, manifest):
    record = json.loads(manifest.read_text())
    if record.get("status") != "OFFLINE_BUILD_VALIDATED_NOT_BOOTED" or record.get("release") != "6.18.60-firefly-rk3399-android17":
        raise ValueError("Missing matching validated RK3399 kernel build")
    for filename, prefix in (("boot/Image", "image"), ("boot/rk3399-firefly-android.dtb", "dtb")):
        path = boot_files / filename
        if digest(path) != record[prefix + "_sha256"] or path.stat().st_size != record[prefix + "_bytes"]:
            raise ValueError("Kernel payload differs from validated build: " + filename)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--boot-medium", choices=("emmc",), default="emmc",
                   help="This candidate targets the original board eMMC only")
    p.add_argument("--product", required=True, type=Path,
                   help="Isolated AOSP out/target/product/rk3399")
    p.add_argument("--boot-files", required=True, type=Path,
                   help="Directory containing boot/ and extlinux/ for FAT")
    p.add_argument("--idbloader", required=True, type=Path)
    p.add_argument("--uboot", required=True, type=Path)
    p.add_argument("--loader-manifest", required=True, type=Path)
    p.add_argument("--kernel-manifest", required=True, type=Path)
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
    required = [a.idbloader, a.uboot, a.simg2img, a.loader_manifest, a.kernel_manifest]
    required += [a.product / f"{n}.img" for n, _ in LAYOUT
                 if n not in ("boot", "metadata")]
    required += [a.boot_files / n for n in (
        "boot/Image", "boot/ramdisk.img", "boot/rk3399-firefly-android.dtb",
        "extlinux/extlinux.conf")]
    for source in required:
        if not source.is_file() or not stat.S_ISREG(source.stat().st_mode):
            p.error(f"Missing ordinary input file: {source}")
    for tool in ("fdtget", "mkfs.vfat", "mcopy", "e2fsck", "mke2fs", "resize2fs"):
        if not shutil.which(tool):
            p.error(f"Required filesystem/DTB tool is missing: {tool}")
    check_boot_files(a.boot_files, a.boot_medium)
    check_kernel_manifest(a.boot_files, a.kernel_manifest)
    check_boot_medium_loaders(a.idbloader, a.uboot, a.loader_manifest, a.boot_files)
    output.parent.mkdir(parents=True, exist_ok=True)
    partitions = []
    offset = 16 * MIB
    for name, size in LAYOUT:
        length = size * MIB if size else TOTAL - MIB - offset
        partitions.append(dict(name=name, offset=offset, size=length))
        offset += length
    result = dict(format=1, board="firefly,firefly-rk3399", hardware_boot_verified=False, boot_medium=a.boot_medium, boot_device=BOOT_MEDIA[a.boot_medium]["device"],
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
