#!/usr/bin/env python3
"""Record the independent kernel build that enables RK3288 reboot modes."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config(path):
    values = {}
    for line in path.read_text().splitlines():
        if match := re.fullmatch(r'(CONFIG_\w+)=(.*)', line):
            values[match[1]] = match[2]
        elif match := re.fullmatch(r'# (CONFIG_\w+) is not set', line):
            values[match[1]] = 'n'
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    port = root.parent
    work = args.work.resolve()
    record_dir = port / 'records/kernel-reboot-mode'
    record_dir.mkdir(exist_ok=True)
    before = config(port / 'records/kernel/config-6.18.60-firefly-android17')
    after = config(work / 'build/.config')
    changes = {name: {'old': before.get(name, 'n'), 'new': after.get(name, 'n')}
               for name in sorted(before.keys() | after.keys()) if before.get(name, 'n') != after.get(name, 'n')}
    assert changes == {'CONFIG_REBOOT_MODE': {'old': 'n', 'new': 'y'},
                       'CONFIG_SYSCON_REBOOT_MODE': {'old': 'n', 'new': 'y'}}, changes
    assert (work / 'firefly-android17.config').read_bytes() == (root / 'firefly-android17.config').read_bytes()
    audit = json.loads((work / 'kernel-audit.json').read_text())
    assert audit['failed'] == 0
    provenance = json.loads((port / 'records/kernel/provenance.json').read_text())
    image_id = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], text=True).strip()
    compiler = subprocess.check_output(['docker', 'run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}', args.image,
                                        'arm-linux-gnueabihf-gcc', '--version'], text=True).splitlines()[0]
    paths = [work / 'build/arch/arm/boot/zImage', work / 'build/arch/arm/boot/dts/rockchip/rk3288-firefly-android17.dtb',
             work / 'build/.config', work / 'binder64-abi-check.o', work / 'build/System.map']
    modules = sorted((work / 'staging').rglob('*.ko'))
    assert len(modules) == audit['modules']
    module_manifest = [{'path': str(path.relative_to(work / 'staging')), 'size_bytes': path.stat().st_size, 'sha256': sha(path)} for path in modules]
    (record_dir / 'module-manifest.json').write_text(json.dumps(module_manifest, indent=2) + '\n')
    record = {
        'purpose': 'Enable Linux syscon reboot target write for existing RK3288 U-Boot Fastboot routing',
        'kernel_version': '6.18.60-firefly-android17', 'configuration_changes': changes,
        'reboot_contract': {'dt_node': '/power-management@ff730000/reboot-mode', 'register': '0xff730094',
                            'command': 'bootloader', 'value': '0x5242c309', 'uboot_result': 'fastboot usb 0'},
        'source': provenance, 'build': {'docker_image': args.image, 'docker_image_id': image_id,
                                      'compiler': compiler, 'jobs': 2, 'cpu_limit': 2,
                                      'timestamp': '2026-10-30 00:00:00 UTC', 'user': 'firefly', 'host': 'builder', 'version': 1},
        'audit': {'passed': audit['passed'], 'failed': audit['failed'], 'modules': audit['modules'],
                  'configuration_requests': audit['configuration_requests'], 'sha256': sha(work / 'kernel-audit.json')},
        'artifacts': {str(path.relative_to(work)): {'size_bytes': path.stat().st_size, 'sha256': sha(path)} for path in paths},
        'inputs': {str(path.relative_to(port)): sha(path) for path in [root / 'firefly-android17.config',
                   root / 'rk3288-firefly-android17.dts', root / 'build-reboot-mode.sh', root / 'scripts/audit-kernel.py',
                   root / 'scripts/check-binder-abi.c', Path(__file__).resolve()]},
        'module_manifest_sha256': sha(record_dir / 'module-manifest.json'),
        'aosp_outputs_installed': False,
    }
    seed = record_dir / 'object-cache-seed.json'
    if seed.is_file():
        record['build']['object_cache_seed'] = json.loads(seed.read_text())
    (record_dir / 'provenance.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'configuration_changes': changes, 'zImage': record['artifacts']['build/arch/arm/boot/zImage'],
                      'audit': record['audit'], 'modules': len(modules)}, indent=2))


if __name__ == '__main__':
    main()
