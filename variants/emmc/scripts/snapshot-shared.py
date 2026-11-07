#!/usr/bin/env python3
"""Capture shared input hashes before building in the private output tree."""
# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
port = root.parents[1]
shared = [
    'bootloader/idbloader.img', 'bootloader/u-boot-dtb.img',
    'bootloader/source/uboot.config', 'kernel/rk3288-firefly-android17.dts',
    'records/kernel-reboot-mode/config-6.18.60-firefly-android17',
    'device/firefly/rk3288/prebuilts/zImage',
    'device/firefly/rk3288/prebuilts/rk3288-firefly-android.dtb', 'boot/extlinux.conf',
]
record = {name: hashlib.sha256((port / name).read_bytes()).hexdigest() for name in shared}
(root / 'records/shared-inputs-before.json').write_text(json.dumps(record, indent=2) + '\n')
