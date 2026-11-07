#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Audit built RK3288 Android kernel artifacts without access to board devices."""
import hashlib
import argparse
import json
import re
import struct
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
ROOT = parser.parse_args().root.resolve()
CHECKS = []


def check(name, value, evidence):
    CHECKS.append({"name": name, "passed": bool(value), "evidence": evidence})


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def read_config(path):
    result = {}
    for line in path.read_text().splitlines():
        match = re.match(r"(CONFIG_\w+)=(.*)", line)
        if match:
            result[match[1]] = match[2]
        match = re.match(r"# (CONFIG_\w+) is not set", line)
        if match:
            result[match[1]] = "n"
    return result


def read_fdt(path):
    data = path.read_bytes()
    magic, size, off_struct, off_strings = struct.unpack_from(">4I", data)
    if magic != 0xD00DFEED or size != len(data):
        raise ValueError("Invalid FDT header")
    string_size, struct_size = struct.unpack_from(">2I", data, 32)
    strings = data[off_strings : off_strings + string_size]
    cursor = off_struct
    end = off_struct + struct_size
    stack = []
    result = {}
    while cursor < end:
        token = struct.unpack_from(">I", data, cursor)[0]
        cursor += 4
        if token == 1:
            stop = data.index(0, cursor)
            stack.append(data[cursor:stop].decode())
            cursor = (stop + 4) & ~3
            result["/" + "/".join(stack[1:])] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, name_offset = struct.unpack_from(">2I", data, cursor)
            cursor += 8
            stop = strings.index(0, name_offset)
            name = strings[name_offset:stop].decode()
            result["/" + "/".join(stack[1:])][name] = data[cursor : cursor + length]
            cursor = (cursor + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            break
        else:
            raise ValueError("Invalid FDT token")
    return result


config = read_config(ROOT / "build/.config")
fragment = read_config(ROOT / "firefly-android17.config")
mismatches = [
    {"symbol": key, "requested": value, "actual": config.get(key, "n")}
    for key, value in fragment.items()
    if config.get(key, "n") != value
]
check("configuration_fragment", not mismatches, {"requested": len(fragment), "mismatches": mismatches})
required = [
    "ANDROID_BINDER_IPC", "ANDROID_BINDERFS", "SECURITY_SELINUX", "AUDIT",
    "BPF_SYSCALL", "BPF_JIT", "BPF_JIT_ALWAYS_ON", "CGROUP_BPF", "BPF_EVENTS",
    "PSI", "MEMCG", "MEMCG_V1", "CPUSETS", "CPUSETS_V1", "SECCOMP_FILTER",
    "NET_CLS_BPF", "NET_ACT_BPF", "NETFILTER_XTABLES_LEGACY", "IP_NF_FILTER",
    "IP_NF_NAT", "IP6_NF_FILTER", "NETFILTER_XT_MATCH_OWNER", "NETFILTER_XT_MATCH_BPF",
    "NET_NS", "PM_WAKELOCKS", "PREEMPT", "FS_ENCRYPTION", "FS_VERITY", "QUOTA",
    "EXT4_FS", "F2FS_FS", "EROFS_FS", "FUSE_FS", "DM_VERITY", "DM_CRYPT",
    "MMC_DW_ROCKCHIP", "REGULATOR_ACT8865", "REGULATOR_FAN53555", "PINCTRL_ROCKCHIP",
    "I2C_RK3X", "DWMAC_ROCKCHIP", "USB_DWC2_DUAL_ROLE", "USB_CONFIGFS_F_FS",
    "USB_HID", "INPUT_EVDEV", "DRM_ROCKCHIP", "ROCKCHIP_DW_HDMI", "DRM_PANFROST",
    "ROCKCHIP_IOMMU", "DMABUF_HEAPS_SYSTEM", "DMABUF_HEAPS_CMA", "SYNC_FILE",
    "SND_SOC_ROCKCHIP_I2S", "DRM_DW_HDMI_I2S_AUDIO", "ZRAM", "ZRAM_BACKEND_LZ4",
    "SYSCON_REBOOT_MODE", "REBOOT_MODE",
]
for symbol in required:
    actual = config.get("CONFIG_" + symbol, "n")
    check("built_in_" + symbol, actual == "y", actual)
check("binder_devices", config.get("CONFIG_ANDROID_BINDER_DEVICES") == '"binder,hwbinder,vndbinder"', config.get("CONFIG_ANDROID_BINDER_DEVICES"))
check("binder_32bit_abi_disabled", config.get("CONFIG_ANDROID_BINDER_IPC_32BIT", "n") == "n", config.get("CONFIG_ANDROID_BINDER_IPC_32BIT", "not present; current kernel uses binder64"))
check("four_cpu_target", config.get("CONFIG_NR_CPUS") == "4", config.get("CONFIG_NR_CPUS"))
check("cpu_arch_armv7", config.get("CONFIG_CPU_V7") == "y", config.get("CONFIG_CPU_V7"))
check("neon", config.get("CONFIG_NEON") == "y", config.get("CONFIG_NEON"))
check("kernel_release", (ROOT / "build/include/config/kernel.release").read_text().strip() == "6.18.60-firefly-android17", (ROOT / "build/include/config/kernel.release").read_text().strip())

zimage = ROOT / "build/arch/arm/boot/zImage"
zdata = zimage.read_bytes()
check("arm_zimage_magic", struct.unpack_from("<I", zdata, 0x24)[0] == 0x016F2818, hex(struct.unpack_from("<I", zdata, 0x24)[0]))
check("arm_zimage_size", len(zdata) > 4 * 1024 * 1024, len(zdata))

dtb = ROOT / "build/arch/arm/boot/dts/rockchip/rk3288-firefly-android17.dtb"
nodes = read_fdt(dtb)


def text_prop(path, prop):
    return nodes[path].get(prop, b"").rstrip(b"\0").decode()


check("original_firefly_compatible", nodes["/"].get("compatible") == b"firefly,firefly-rk3288\0rockchip,rk3288\0", text_prop("/", "compatible").replace("\0", ","))
check("original_firefly_model", text_prop("/", "model") == "Firefly-RK3288", text_prop("/", "model"))
check("emmc_disabled", text_prop("/mmc@ff0f0000", "status") == "disabled", text_prop("/mmc@ff0f0000", "status"))
for path in ["/mmc@ff0c0000", "/hdmi@ff980000", "/gpu@ffa30000", "/ethernet@ff290000", "/usb@ff580000", "/usb@ff540000", "/vop@ff930000", "/vop@ff940000", "/i2s@ff890000"]:
    check("dt_enabled_" + path, text_prop(path, "status") == "okay", text_prop(path, "status"))
check("adb_otg_peripheral", text_prop("/usb@ff580000", "dr_mode") == "peripheral", text_prop("/usb@ff580000", "dr_mode"))
check("usb_host_preserved", text_prop("/usb@ff540000", "dr_mode") == "host", text_prop("/usb@ff540000", "dr_mode"))
check("sd_clock_50mhz", nodes["/mmc@ff0c0000"]["max-frequency"] == struct.pack(">I", 50000000), struct.unpack(">I", nodes["/mmc@ff0c0000"]["max-frequency"])[0])
check("serial_console", text_prop("/chosen", "stdout-path") == "serial2:115200n8", text_prop("/chosen", "stdout-path"))
check("hdmi_audio_card", text_prop("/hdmi-sound", "compatible") == "simple-audio-card", text_prop("/hdmi-sound", "compatible"))
check("hdmi_audio_format", text_prop("/hdmi-sound", "simple-audio-card,format") == "i2s", text_prop("/hdmi-sound", "simple-audio-card,format"))
reboot_path = "/power-management@ff730000/reboot-mode"
check("syscon_reboot_mode_compatible", text_prop(reboot_path, "compatible") == "syscon-reboot-mode", text_prop(reboot_path, "compatible"))
check("syscon_reboot_mode_register_offset", nodes[reboot_path].get("offset") == struct.pack(">I", 0x94), "PMU 0xff730000 + offset 0x94 = U-Boot 0xff730094")
check("syscon_reboot_mode_bootloader_fastboot", nodes[reboot_path].get("mode-bootloader") == struct.pack(">I", 0x5242c309), "bootloader -> BOOT_FASTBOOT (0x5242c309)")
system_map = (ROOT / "build/System.map").read_text().splitlines()
for symbol in ["reboot_mode_notify", "syscon_reboot_mode_driver"]:
    check("linked_" + symbol, any(line.endswith(" " + symbol) for line in system_map), symbol)
module_root = ROOT / "staging/lib/modules/6.18.60-firefly-android17"
modules = list(module_root.rglob("*.ko"))
check("modules_installed", len(modules) > 0, len(modules))
check("modules_order", (module_root / "modules.order").is_file(), str(module_root / "modules.order"))
check("modules_dep", (module_root / "modules.dep").is_file(), str(module_root / "modules.dep"))
check("modules_alias", (module_root / "modules.alias").is_file(), str(module_root / "modules.alias"))
check("modules_builtin", (module_root / "modules.builtin").is_file(), str(module_root / "modules.builtin"))
abi = (ROOT / "binder64-abi-check.o").read_bytes()
check("binder64_arm32_compile", abi[:5] == b"\x7fELF\x01" and struct.unpack_from("<H", abi, 18)[0] == 40, "ARM32 compile-time assertions require 8-byte Binder pointers/sizes and protocol 8")
report = {
    "scope": "Kernel compilation and static configuration/DTB/artifact checks",
    "board_boot": "pending",
    "kernel_version": "6.18.60-firefly-android17",
    "configuration_requests": len(fragment),
    "modules": len(modules),
    "artifacts": [{"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)} for path in [zimage, dtb, ROOT / "build/.config"]],
    "checks": CHECKS,
    "passed": sum(item["passed"] for item in CHECKS),
    "failed": sum(not item["passed"] for item in CHECKS),
}
(ROOT / "kernel-audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
print(json.dumps({"passed": report["passed"], "failed": report["failed"], "modules": len(modules)}))
for item in CHECKS:
    if not item["passed"]:
        print(json.dumps(item, ensure_ascii=False))
raise SystemExit(bool(report["failed"]))
