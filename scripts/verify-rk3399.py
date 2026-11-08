#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only verification of the original Firefly-RK3399 eMMC candidate.

Shares only architecture-neutral file/GPT/ext4/cpio readers with verify-sd.py.
Does not import the assembler or inherit RK3288 boot/ELF/product checks.
An offline pass never means that the board, YouTube or a decoder has booted.
"""
import argparse
import gzip
import importlib.util
import io
import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET

_spec = importlib.util.spec_from_file_location("image_readers", Path(__file__).with_name("verify-sd.py"))
v = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v)
BOOT_FILES = ("boot/Image", "boot/ramdisk.img", "boot/rk3399-firefly-android.dtb", "extlinux/extlinux.conf")
BOOTCMD = "bootflow scan -lbG mmc0"


def elf64(path, installed_path=None):
    size = path.stat().st_size
    with v.opened(path) as stream:
        raw = stream.read(64)
        if len(raw) != 64 or raw[:7] != b"\x7fELF\x02\x01\x01":
            raise v.VerificationError("Not a little-endian ELF64: " + str(path))
        (_, kind, machine, version, _, phoff, _, _, ehsize, phsize, count, _, _, _) = struct.unpack("<16sHHIQQQIHHHHHH", raw)
        if (kind not in (2, 3) or machine != 183 or version != 1 or ehsize != 64
                or phsize != 56 or not count or phoff + phsize * count > size):
            raise v.VerificationError("Invalid AArch64 ELF/program headers: " + str(path))
        stream.seek(phoff)
        headers = stream.read(phsize * count)
        executable, interpreter = False, None
        for i in range(count):
            ptype, flags, offset, _, _, filesz, memsz, _ = struct.unpack_from("<IIQQQQQQ", headers, i * phsize)
            if ptype in (1, 3) and (offset + filesz > size or filesz > memsz):
                raise v.VerificationError("ELF segment exceeds file or memory")
            executable |= ptype == 1 and bool(flags & 1)
            if ptype == 3:
                stream.seek(offset)
                interpreter = stream.read(filesz).rstrip(b"\0").decode()
        allowed = (None, "/system/bin/linker64")
        if installed_path == "/system/bin/init":
            allowed += ("/system/bin/bootstrap/linker64",)
        if not executable or interpreter not in allowed:
            raise v.VerificationError("Invalid AArch64 load segment or interpreter")
    return {"class": "ELF64", "machine": "AArch64", "bytes": size,
            "interpreter": interpreter, "sha256": v.digest(path)}


def loaders(a, audit):
    record = json.loads(a.loader_manifest.read_text(), object_pairs_hook=v.unique_json)
    audit.stage = "rk3399-loaders"
    audit.check("loader-target", record.get("status") == "OFFLINE_BUILD_VALIDATED_NOT_BOOTED"
                and record.get("board") == "original Firefly-RK3399 DDR3"
                and record.get("spl_boot_order") == "/mmc@fe330000 only"
                and record.get("environment") == "nowhere")
    env = record["default_environment"]
    audit.check("emmc-autoboot", env.get("boot_targets") == "mmc0" and env.get("bootcmd") == BOOTCMD, env)
    for path, filename, offset, capacity in ((a.idbloader, "idbloader.img", 32768, 8 * v.MIB - 32768),
                                            (a.uboot, "u-boot.itb", 8 * v.MIB, 8 * v.MIB)):
        entry, size = record["assets"][filename], path.stat().st_size
        audit.check("validated-loader:" + filename, 0 < size <= capacity
                    and size == entry["bytes"] and v.digest(path) == entry["sha256"])
        audit.check("on-disk-loader:" + filename, v.digest(a.image, offset, size) == entry["sha256"])
        audit.check("loader-padding-zero:" + filename, v.zero_region(a.image, offset + size, capacity - size))
    audit.check("gpt-to-loader-gap-zero", v.zero_region(a.image, 34 * 512, 32768 - 34 * 512))
    audit.check("uboot-is-fit", v.read_at(a.uboot, 0, 4) == bytes.fromhex("d00dfeed"))
    return env


def boot(fat, source_dir, env, scratch, audit):
    audit.stage = "rk3399-boot"
    audit.run("fat-readonly-fsck", "fsck.fat", "-n", fat)
    sources = {str(p.relative_to(source_dir)): v.regular(p) for p in source_dir.rglob("*") if p.is_file()}
    audit.check("mandatory-boot-files", set(BOOT_FILES) <= sources.keys())
    result = audit.run("fat-list", "mdir", "-a", "-/", "-b", "-i", fat, "::/")
    members = {s[3:].casefold() for s in result.stdout.decode().splitlines() if s.startswith("::/") and not s.endswith("/")}
    audit.check("fat-inventory-matches-inputs", members == {s.casefold() for s in sources})
    extracted = {}
    for i, (name, source) in enumerate(sorted(sources.items())):
        if any(c in name for c in "\r\n*?[]"):
            raise v.VerificationError("Unsupported FAT filename")
        dest = scratch / ("boot-member-" + str(i))
        audit.run("fat-extract:" + name, "mcopy", "-i", fat, "::/" + name, dest)
        audit.check("boot-input-hash:" + name, v.digest(dest) == v.digest(source))
        extracted[name] = dest
    kernel = extracted["boot/Image"]
    header = v.read_at(kernel, 0, 64)
    image_size = struct.unpack_from("<Q", header, 16)[0]
    text_offset = struct.unpack_from("<Q", header, 8)[0]
    image_flags = struct.unpack_from("<Q", header, 24)[0]
    audit.check("arm64-image", header[56:60] == b"ARM\x64" and image_size > 0,
                {"file_bytes": kernel.stat().st_size, "memory_bytes": image_size})
    audit.check("booti-kernel-placement", text_offset == 0 and bool(image_flags & 8)
                and (int(env["kernel_addr_r"], 16) - text_offset) % 0x200000 == 0)
    windows = [(int(env["kernel_addr_r"], 16), max(image_size, kernel.stat().st_size)),
               (int(env["ramdisk_addr_r"], 16), extracted["boot/ramdisk.img"].stat().st_size),
               (int(env["fdt_addr_r"], 16), extracted["boot/rk3399-firefly-android.dtb"].stat().st_size)]
    audit.check("boot-payload-load-windows", all(start > 0 and start + size < 0xf8000000 for start, size in windows)
                and all(start >= other + count or other >= start + size
                        for i, (start, size) in enumerate(windows) for other, count in windows[:i]), windows)
    dtb = extracted["boot/rk3399-firefly-android.dtb"]
    for node, prop, required in (("/", "compatible", "firefly,firefly-rk3399"),
                                  ("/mmc@fe330000", "status", "okay"),
                                  ("/rt5640-sound", "simple-audio-card,name", "FireflyRT5640"),
                                  ("/hdmi-sound", "simple-audio-card,name", "FireflyHDMI"),
                                  ("/hdmi-sound", "status", "okay"),
                                  ("/i2c@ff3d0000/typec-portc@22/connector", "data-role", "device"),
                                  ("/usb@fe800000/usb@fe800000", "dr_mode", "peripheral"),
                                  ("/usb@fe800000/usb@fe800000", "maximum-speed", "high-speed")):
        value = audit.run("dtb:" + node + ":" + prop, "fdtget", "-t", "s", dtb, node, prop).stdout.decode().strip()
        audit.check("dtb-value:" + node + ":" + prop, required in value.split(), value)
    directives = {}
    for line in extracted["extlinux/extlinux.conf"].read_text().splitlines():
        fields = line.split("#", 1)[0].strip().split(None, 1)
        if len(fields) == 2:
            directives.setdefault(fields[0].upper(), []).append(fields[1])
    for key, value in (("LINUX", "/boot/Image"), ("INITRD", "/boot/ramdisk.img"), ("FDT", "/boot/rk3399-firefly-android.dtb")):
        audit.check("extlinux:" + key, directives.get(key) == [value])
    append = directives.get("APPEND", [])
    audit.check("single-boot-command-line", len(append) == 1)
    tokens = append[0].split()
    for key, value in (("androidboot.hardware", "fireflyrk3399"), ("androidboot.boot_devices", "fe330000.mmc")):
        audit.check("cmdline:" + key, [t for t in tokens if t.startswith(key + "=")] == [key + "=" + value])
    audit.check("serial-console", "console=ttyS2,1500000n8" in tokens)
    with gzip.GzipFile(fileobj=io.BytesIO(extracted["boot/ramdisk.img"].read_bytes())) as stream:
        raw = stream.read(512 * v.MIB + 1)
    audit.check("bounded-ramdisk", len(raw) <= 512 * v.MIB)
    entries = v.parse_cpio(raw)
    init = entries.get("init", {})
    audit.check("first-stage-init-mode", stat.S_ISREG(init.get("mode", 0)) and bool(init.get("mode", 0) & 0o111)
                and init.get("uid") == 0 and init.get("gid") == 0)
    dest = scratch / "first-stage-init"
    dest.write_bytes(init["data"])
    audit.check("first-stage-init-aarch64", True, elf64(dest))
    v.check_fstab(entries["fstab.fireflyrk3399"]["data"], audit, "ramdisk-fstab")


def android(filesystems, audit):
    system, vendor = filesystems["system"], filesystems["vendor"]
    audit.stage = "rk3399-android"
    prop_path = v.pick(system, ("/system/build.prop", "/build.prop"), audit, "system-properties")
    system.mount_prefix = None if prop_path.startswith("/system/") else "system"
    props = v.properties(system.read(prop_path))
    for key, expected in (("ro.build.version.sdk", "37"), ("ro.adb.secure", "1"), ("ro.zygote", "zygote64_32")):
        audit.check(key, props.get(key) == expected, props.get(key))
    init = v.pick(system, ("/system/bin/init", "/bin/init"), audit, "second-stage-init")
    _, binary = system.dump(init)
    info = elf64(binary, "/system/bin/init")
    audit.check("second-stage-init-aarch64", True, info)
    if info["interpreter"] == "/system/bin/bootstrap/linker64":
        path = "/system/bin/bootstrap/linker64" if system.mount_prefix is None else "/bin/bootstrap/linker64"
        _, binary = system.dump(path)
        audit.check("bootstrap-linker-aarch64", elf64(binary)["interpreter"] is None)
    vprops = v.properties(vendor.read("/build.prop"))
    for key, value in (("ro.hardware.egl", "mesa"), ("ro.hardware.gralloc", "minigbm"),
                       ("ro.hardware.hwcomposer", "drm"), ("persist.sys.usb.config", "adb")):
        audit.check(key, vprops.get(key) == value, vprops.get(key))
    abi = {**props, **vprops}
    audit.check("primary-abi-arm64", abi.get("ro.product.cpu.abilist64") == "arm64-v8a", abi.get("ro.product.cpu.abilist64"))
    audit.check("secondary-abi-arm32", "armeabi-v7a" in abi.get("ro.product.cpu.abilist32", "").split(","))
    members = ["/lib64/egl/libEGL_mesa.so", "/lib64/egl/libGLESv2_mesa.so",
               "/lib64/libavcodec.so", "/lib64/libavutil.so", "/lib64/libswscale.so", "/lib64/libswresample.so",
               "/bin/hw/android.hardware.media.c2-service-firefly", "/bin/hw/android.hardware.audio.service-aidl.firefly",
               "/bin/hw/android.hardware.graphics.allocator-service.minigbm", "/bin/hw/android.hardware.composer.hwc3-service.drm",
               "/bin/firefly-vpu-probe", "/bin/firefly-hwdecode"]
    for path in members:
        real, binary = vendor.dump(path)
        audit.check("vendor-aarch64:" + path, True, elf64(binary))
        if path.startswith("/bin/"):
            audit.check("vendor-executable:" + path, bool(vendor.inode(real)["mode"] & 0o111))
    v.check_fstab(vendor.read("/etc/fstab.fireflyrk3399"), audit, "vendor-fstab")
    init_rc = vendor.read("/etc/init/hw/init.fireflyrk3399.rc").decode()
    audit.check("board-init-has-no-rk3288-addresses", not any(x in init_rc for x in ("rk3288", "ff0f0000", "ff580000")))
    policy = vendor.read("/etc/audio_policy_configuration.xml").decode()
    ports = ET.fromstring(policy).findall("./modules/module/devicePorts/devicePort")
    audit.check("rt5640-policy", any(p.get("address") == "firefly-rt5640" for p in ports)
                and any(p.get("type") == "AUDIO_DEVICE_OUT_AUX_DIGITAL" and p.get("address") == "" for p in ports)
                and "es8323" not in policy.lower())
    codecs = vendor.read("/etc/media_codecs_firefly.xml").decode()
    audit.check("rkvdec-codecs", "video/x-vnd.on2.vp9" in codecs and "video/avc" in codecs and "video/hevc" not in codecs)
    audit.data["android"] = {"sdk": 37, "architecture": "arm64", "secondary_apps": "arm", "hardware_tested": False}


def verify(a, audit, scratch):
    a.image = v.regular(a.image)
    manifest_path = v.regular(a.manifest or a.image.with_suffix(a.image.suffix + ".json"))
    manifest = json.loads(manifest_path.read_text(), object_pairs_hook=v.unique_json)
    audit.check("image-size", a.image.stat().st_size == v.DISK_BYTES)
    audit.check("image-target", manifest.get("format") == 1 and manifest.get("board") == "firefly,firefly-rk3399"
                and manifest.get("boot_medium") == "emmc" and manifest.get("boot_device") == "fe330000.mmc"
                and manifest.get("image_size") == v.DISK_BYTES and manifest.get("hardware_boot_verified") is False)
    inputs = [a.idbloader, a.uboot, a.loader_manifest, a.kernel_manifest, *[a.boot_files / name for name in BOOT_FILES],
              *[a.product / (name + ".img") for name in ("system", "system_ext", "product", "vendor", "userdata")]]
    inputs = [v.regular(path) for path in inputs]
    observations = {p: v.snapshot(p) for p in [a.image, manifest_path, *inputs]}
    for path in inputs:
        v.source_manifest_hash(path, manifest, audit)
    kernel = json.loads(a.kernel_manifest.read_text(), object_pairs_hook=v.unique_json)
    audit.check("validated-kernel-release", kernel.get("status") == "OFFLINE_BUILD_VALIDATED_NOT_BOOTED"
                and kernel.get("release") == "6.18.60-firefly-rk3399-android17")
    for filename, prefix in (("boot/Image", "image"), ("boot/rk3399-firefly-android.dtb", "dtb")):
        source = a.boot_files / filename
        audit.check("validated-kernel-input:" + prefix, source.stat().st_size == kernel[prefix + "_bytes"]
                    and v.digest(source) == kernel[prefix + "_sha256"])
    partitions = v.parse_gpt(a.image, audit)
    env = loaders(a, audit)
    records = {p["name"]: p for p in manifest["partitions"]}
    audit.check("partition-set", len(manifest["partitions"]) == 7 and set(records) == {x[0] for x in v.EXPECTED})
    payloads = {}
    for part in partitions:
        name = part["name"]
        audit.stage = "partition:" + name
        record = records[name]
        audit.check("manifest-partition:" + name, all(record[k] == part[k] for k in ("offset", "size", "uuid")))
        size = record["filesystem_image_bytes"]
        audit.check("partition-bounds:" + name, type(size) is int and 0 < size <= part["size"])
        path = scratch / (name + ".img")
        actual = v.extract_region(a.image, path, part["offset"], size)
        audit.check("partition-hash:" + name, actual == record["filesystem_sha256"])
        audit.check("partition-tail-zero:" + name, v.zero_region(a.image, part["offset"] + size, part["size"] - size))
        payloads[name] = path
        if name == "boot":
            boot(path, a.boot_files, env, scratch, audit)
            continue
        sb = v.superblock(path)
        audit.check("ext4-size:" + name, 0 < sb["filesystem_bytes"] <= size)
        audit.run("readonly-fsck:" + name, "e2fsck", "-f", "-n", path)
        if name == "metadata":
            tree = v.Ext4(path, scratch, "metadata").inventory()
            audit.check("metadata-empty", set(tree) <= {"/", "/lost+found"} and all(x["type"] == "directory" for x in tree.values()))
            continue
        source = v.raw_source(a.product / (name + ".img"), scratch, a.simg2img, audit)
        if name == "userdata":
            audit.check("userdata-expanded", sb["uuid"] == v.superblock(source)["uuid"]
                        and sb["filesystem_bytes"] == size == part["size"])
            audit.check("userdata-tree-preserved", v.Ext4(source, scratch, "data").inventory() == v.Ext4(path, scratch, "data").inventory())
        else:
            audit.check("aosp-payload-identical:" + name, source.stat().st_size == size and v.digest(source) == actual)
    android({name: v.Ext4(payloads[name], scratch, None if name == "system" else name)
             for name in ("system", "system_ext", "product", "vendor")}, audit)
    audit.stage = "delivery"
    actual = v.digest(a.image)
    audit.check("whole-image-sha256", actual == manifest["image_sha256"], actual)
    audit.check("inputs-remained-unchanged", all(v.snapshot(p) == value for p, value in observations.items()))
    audit.data.update(image_verified=True, image_sha256=actual, board_boot="pending")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("image", "product", "boot-files", "idbloader", "uboot", "loader-manifest", "kernel-manifest", "report"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--simg2img", type=Path)
    p.add_argument("--scratch-parent", type=Path)
    a = p.parse_args()
    if a.report.exists():
        p.error("Report must be a new file")
    audit = v.Audit("original-firefly-rk3399-emmc-offline")
    status = 1
    try:
        v.preflight(audit)
        with tempfile.TemporaryDirectory(prefix="verify-rk3399-", dir=a.scratch_parent) as temp:
            verify(a, audit, Path(temp))
        audit.finish("PASS_OFFLINE_NOT_BOOTED")
        status = 0
    except Exception as error:
        audit.data["error"] = str(error)
        audit.finish("FAIL")
    a.report.parent.mkdir(parents=True, exist_ok=True)
    with a.report.open("x", encoding="utf-8") as stream:
        json.dump(audit.data, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"result": audit.data["result"], "report": str(a.report), "error": audit.data.get("error")}))
    return status


if __name__ == "__main__":
    sys.exit(main())
