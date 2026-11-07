#!/usr/bin/env python3
"""Check the current port kernel against actual U-Boot load addresses."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kernel-work', type=Path, required=True)
    args = parser.parse_args()
    port = Path(__file__).resolve().parents[2]
    system_map = args.kernel_work / 'build/System.map'
    symbols = {}
    for line in system_map.read_text().splitlines():
        values = line.split()
        if len(values) == 3 and values[2] in ['_text', '__bss_start', '_end']:
            symbols[values[2]] = int(values[0], 16)
    assert set(symbols) == {'_text', '__bss_start', '_end'}
    config = (args.kernel_work / 'build/.config').read_text()
    offset = int(re.search(r'^CONFIG_PAGE_OFFSET=(0x[\dA-Fa-f]+)$', config, re.M)[1], 16)
    assert offset == 0xc0000000
    addresses = None
    inputs = {}
    for path in [port / 'bootloader/u-boot-dtb.img', port / 'variants/emmc/bootloader/u-boot-dtb.img']:
        data = path.read_bytes()
        found = {}
        for name in ['kernel_addr_r', 'fdt_addr_r', 'ramdisk_addr_r']:
            values = {int(value, 16) for value in re.findall(name.encode() + rb'=(0x[0-9a-fA-F]+)\x00', data)}
            assert len(values) == 1, (path, name, values)
            found[name] = values.pop()
        assert addresses is None or found == addresses
        addresses = found
        inputs[str(path.relative_to(port))] = sha(path)
    kernel = port / 'device/firefly/rk3288/prebuilts/zImage'
    assert sha(kernel) == sha(args.kernel_work / 'build/arch/arm/boot/zImage')
    dtbs = [port / 'device/firefly/rk3288/prebuilts/rk3288-firefly-android.dtb',
            port / 'variants/emmc/boot/rk3288-firefly-android.dtb']
    end = symbols['_end'] - offset
    gap = addresses['fdt_addr_r'] - end
    dtb_nonoverlap = all(addresses['fdt_addr_r'] + dtb.stat().st_size <= addresses['kernel_addr_r'] for dtb in dtbs)
    kernel_nonoverlap = addresses['kernel_addr_r'] + kernel.stat().st_size <= addresses['ramdisk_addr_r']
    assert gap > 0 and dtb_nonoverlap and kernel_nonoverlap
    record = {
        'scope': 'static-built-kernel-and-uboot-address-check',
        'latest_kernel_record': 'records/kernel-reboot-mode/provenance.json',
        'kernel_virtual_symbols': {name: hex(value) for name, value in symbols.items()},
        'assumed_virtual_offset': hex(offset), 'kernel_physical_end': hex(end),
        'uboot_default_load_addresses': {name: hex(value) for name, value in addresses.items()},
        'dtb_after_kernel_end_gap_bytes': gap, 'dtb_to_compressed_kernel_nonoverlap': dtb_nonoverlap,
        'compressed_kernel_to_ramdisk_nonoverlap': kernel_nonoverlap, 'pass': True,
        'ramdisk_size_check': 'performed separately against the actual product ramdisk during image validation',
        'kernel_sha256': sha(kernel), 'System_map_sha256': sha(system_map),
        'config_sha256': sha(args.kernel_work / 'build/.config'), 'uboot_sha256': inputs,
        'dtb_sha256': {str(path.relative_to(port)): sha(path) for path in dtbs},
    }
    (port / 'records/boot-load-addresses.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'kernel_physical_end': hex(end), 'DTB_gap_bytes': gap, 'pass': True}))


if __name__ == '__main__':
    main()
