#!/usr/bin/env python3
"""Inspect emitted eMMC boot assets and record their reproducible inputs."""
# SPDX-License-Identifier: MIT
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import zlib
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT.parents[1]
BOOTCMD = 'mmc dev 0 && mmc rescan && sysboot mmc 0:1 any ${scriptaddr} /extlinux/extlinux.conf'
EMMC = '/mmc@ff0f0000'
SD = '/mmc@ff0c0000'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def prop(path, node, name, kind='s'):
    return run('fdtget', '-t', kind, str(path), node, name)


def absent(path, node, name):
    return subprocess.run(['fdtget', str(path), node, name], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode != 0


def inspect_mmc(path):
    assert prop(path, EMMC, 'status') == 'okay'
    assert prop(path, EMMC, 'max-frequency', 'u') == '50000000'
    assert prop(path, EMMC, 'bus-width', 'u') == '8'
    assert prop(path, SD, 'status') == 'disabled'
    for capability in ['mmc-hs200-1_8v', 'mmc-hs200-1_2v', 'mmc-hs400-1_8v',
                       'mmc-hs400-1_2v', 'mmc-ddr-1_8v', 'mmc-ddr-1_2v']:
        assert absent(path, EMMC, capability), capability
    return {name: prop(path, EMMC, name, kind) for name, kind in [
        ('status', 's'), ('compatible', 's'), ('max-frequency', 'u'),
        ('bus-width', 'u'), ('pinctrl-0', 'x'), ('vmmc-supply', 'x'), ('vqmmc-supply', 'x')]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--jobs', type=int, choices=[1, 2], default=2)
    parser.add_argument('--shared-kernel-update', action='store_true',
                        help='Audit unchanged boot assets after promoting an independently built shared kernel')
    args = parser.parse_args()
    build = ROOT / 'out/uboot'
    config = (ROOT / 'configs/uboot.config').read_text().splitlines()
    required = ['CONFIG_ENV_IS_NOWHERE=y', 'CONFIG_MISC_INIT_R=y', 'CONFIG_MISC=y',
                'CONFIG_ROCKCHIP_EFUSE=y', 'CONFIG_HASH=y', 'CONFIG_SHA256=y',
                'CONFIG_CMD_SYSBOOT=y', 'CONFIG_CMD_MMC=y', 'CONFIG_HUSH_PARSER=y',
                'CONFIG_BOOTCOMMAND="' + BOOTCMD + '"',
                'CONFIG_LOCALVERSION="-firefly-android-emmc1"']
    assert all(line in config for line in required), [s for s in required if s not in config]
    for line in config:
        if line.startswith('CONFIG_ENV_IS_IN_') or line.startswith(('CONFIG_CMD_FUSE=', 'CONFIG_MMC_HS200_SUPPORT=', 'CONFIG_MMC_HS400_SUPPORT=')):
            assert not line.endswith('=y'), line
    kernel_config = (ROOT / 'configs/kernel.config').read_bytes()
    assert kernel_config == (PORT / 'records/kernel-reboot-mode/config-6.18.60-firefly-android17').read_bytes()
    for flag in [b'CONFIG_MMC=y', b'CONFIG_MMC_BLOCK=y', b'CONFIG_MMC_DW=y',
                 b'CONFIG_MMC_DW_ROCKCHIP=y', b'CONFIG_PINCTRL_ROCKCHIP=y',
                 b'CONFIG_ROCKCHIP_IODOMAIN=y', b'CONFIG_REGULATOR_ACT8865=y',
                 b'CONFIG_SYSCON_REBOOT_MODE=y', b'CONFIG_REBOOT_MODE=y']:
        assert flag in kernel_config.splitlines(), flag

    linux_dtb = ROOT / 'boot/rk3288-firefly-android.dtb'
    linux_mmc = inspect_mmc(linux_dtb)
    assert prop(linux_dtb, '/', 'compatible') == 'firefly,firefly-rk3288 rockchip,rk3288'
    assert prop(linux_dtb, '/usb@ff580000', 'dr_mode') == 'peripheral'
    # Board supplies and pinctrl are inherited from the upstream original board.
    for name in ['vmmc-supply', 'vqmmc-supply', 'pinctrl-0']:
        assert linux_mmc[name]
    main_mmc = inspect_mmc(build / 'u-boot.dtb')
    spl_dtb = build / 'spl/u-boot-spl.dtb'
    assert prop(spl_dtb, '/chosen', 'u-boot,spl-boot-order') == EMMC
    assert prop(build / 'u-boot.dtb', '/chosen', 'u-boot,spl-boot-order') == EMMC
    for dtb in [build / 'u-boot.dtb', spl_dtb]:
        assert prop(dtb, '/aliases', 'mmc0') == EMMC
        assert prop(dtb, EMMC, 'status') == 'okay'
        assert prop(dtb, EMMC, 'max-frequency', 'u') == '50000000'
        assert prop(dtb, SD, 'status') == 'disabled'
    assert prop(build / 'u-boot.dtb', '/efuse@ffb40000', 'compatible') == 'rockchip,rk3288-efuse'
    symbols = run('arm-linux-gnueabihf-nm', str(build / 'u-boot'))
    identity_symbols = ['misc_init_r', 'rockchip_cpuid_from_efuse', 'rockchip_cpuid_set',
                        'rockchip_setup_macaddr', 'fdt_root', 'fdt_fixup_ethernet']
    assert any(line.endswith(' T misc_init_r') for line in symbols.splitlines())
    for symbol in identity_symbols:
        assert any(line.endswith(' ' + symbol) for line in symbols.splitlines()), symbol
    (ROOT / 'records/identity-symbols.txt').write_text('\n'.join(
        line for line in symbols.splitlines() if any(line.endswith(' ' + s) for s in identity_symbols)) + '\n')
    image = (ROOT / 'bootloader/u-boot-dtb.img').read_bytes()
    magic, hcrc, timestamp, size, load, entry, dcrc = struct.unpack('>7I', image[:28])
    assert magic == 0x27051956 and len(image) == size + 64
    assert timestamp == 1704672000 and image[29] == 2
    header = bytearray(image[:64]); header[4:8] = b'\0' * 4
    assert zlib.crc32(header) == hcrc and zlib.crc32(image[64:]) == dcrc
    assert b'bootcmd=' + BOOTCMD.encode() + b'\0' in image
    assert b'bootcmd=setenv boot_targets mmc1;' not in image
    idb = (ROOT / 'bootloader/idbloader.img').read_bytes()
    spl_bytes = spl_dtb.read_bytes()
    offset = idb.find(spl_bytes)
    assert offset >= 0 and idb.find(spl_bytes, offset + 1) == -1
    shutil.copyfile(spl_dtb, ROOT / 'records/uboot-spl.dtb')
    extlinux = (ROOT / 'boot/extlinux.conf').read_text()
    assert 'androidboot.boot_devices=ff0f0000.mmc' in extlinux
    assert 'ff0c0000.mmc' not in extlinux and 'androidboot.serialno=${serial#}' in extlinux
    baseline = json.loads((ROOT / 'records/shared-inputs-before.json').read_text())
    assert all(sha(PORT / name) == value for name, value in baseline.items())
    identity = json.loads((ROOT / 'records/identity-init-validation.json').read_text())
    assert identity['result'] == 'passed'
    media_contract = json.loads((ROOT / 'records/media-contract-validation.json').read_text())
    assert media_contract['result'] == 'passed' and media_contract['checks_failed'] == 0
    assert all(sha(PORT / name) == value for name, value in media_contract['inputs'].items())

    record = {
        'variant': 'emmc', 'board': 'firefly,firefly-rk3288',
        'boot_devices': 'ff0f0000.mmc', 'bootcmd': BOOTCMD,
        'extlinux': {'device': 'mmc', 'devnum': 0, 'partition': 1, 'path': '/extlinux/extlinux.conf'},
        'image_layout_bytes': 12 * 1024 ** 3, 'minimum_target_bytes': 12 * 1024 ** 3,
        'kernel': {'version': '6.18.60-firefly-android17', 'compiled': 'DTB only',
                   'zImage': {'path': 'device/firefly/rk3288/prebuilts/zImage',
                              'size_bytes': (PORT / 'device/firefly/rk3288/prebuilts/zImage').stat().st_size,
                              'sha256': sha(PORT / 'device/firefly/rk3288/prebuilts/zImage')},
                   'source_archive_sha256': '3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e'},
        'uboot': {'version': 'v2024.01', 'defconfig': 'firefly-rk3288_defconfig',
                  'source_archive_sha256': 'a03c3c2ba9d2bea5176c6406f1f3429a79e1147be242f5a07dbd9e89b3cc83c4',
                  'source_date_epoch': 1704672000, 'environment': 'nowhere; RAM only',
                  'spl_boot_order': [EMMC], 'spl_dtb_sha256': sha(spl_dtb),
                  'spl_dtb_offset_in_idbloader_bytes': offset, 'main_mmc': main_mmc},
        'build': {'docker_image': args.image,
                  'docker_image_id': (ROOT / 'records/builder-image-id.txt').read_text().strip(),
                  'cpu_limit': 2, 'jobs': args.jobs,
                  'cross_compiler': run('arm-linux-gnueabihf-gcc', '--version').splitlines()[0]},
        'checks': {'linux_mmc': linux_mmc, 'sd_disabled': True,
                   'no_hs200_hs400_ddr_properties': True, 'legacy_header_crc': True,
                   'legacy_payload_crc': True, 'spl_dtb_embedded_in_idbloader': True,
                   'shared_kernel_config_matches_latest_build': True, 'shared_inputs_unchanged': baseline,
                   'identity_fault_injection': identity,
                   'shared_media_contract': {'result': media_contract['result'],
                                             'checks_passed': media_contract['checks_passed'],
                                             'sha256': sha(ROOT / 'records/media-contract-validation.json')}},
        'inputs': {}, 'artifacts': {},
    }
    for path in sorted((ROOT / 'patches').glob('*.patch')):
        record['inputs'][str(path.relative_to(ROOT))] = sha(path)
    for name in ['rebuild.sh', 'rk3288-firefly-android17-emmc.dts', 'configs/kernel.config',
                 'configs/uboot.config', 'scripts/record-build.py', 'scripts/set-bootcommand.py',
                 'scripts/snapshot-shared.py',
                 'tests/test-identity-init.py', 'tests/check-media-contract.py']:
        record['inputs'][name] = sha(ROOT / name)
    for name in ['boot/rk3288-firefly-android.dtb', 'boot/extlinux.conf',
                 'bootloader/idbloader.img', 'bootloader/u-boot-dtb.img', 'records/uboot-spl.dtb']:
        path = ROOT / name
        record['artifacts'][name] = {'size_bytes': path.stat().st_size, 'sha256': sha(path)}
    record['kernel']['latest_build_record'] = 'records/kernel-reboot-mode/provenance.json'
    record['kernel']['shared_config_sha256'] = sha(ROOT / 'configs/kernel.config')
    if args.shared_kernel_update:
        initial_path = ROOT / 'records/boot-assets-initial.json'
        initial = json.loads(initial_path.read_text())
        for name in ['boot/rk3288-firefly-android.dtb', 'bootloader/idbloader.img', 'bootloader/u-boot-dtb.img']:
            assert record['artifacts'][name] == initial['artifacts'][name], name
        record['build'] = initial['build']
        record['kernel']['dtb_build_config_sha256'] = initial['inputs']['configs/kernel.config']
        record['shared_kernel_update'] = {
            'recorded_at': datetime.now(timezone.utc).isoformat(),
            'boot_assets_recompiled': False,
            'initial_boot_asset_record': 'records/boot-assets-initial.json',
            'initial_boot_asset_record_sha256': sha(initial_path),
            'previous_shared_zImage': initial['kernel']['zImage'],
            'latest_shared_kernel_record_sha256': sha(PORT / 'records/kernel-reboot-mode/provenance.json'),
            'initial_DTB_config': 'configs/kernel-initial.config',
            'initial_DTB_config_sha256': sha(ROOT / 'configs/kernel-initial.config'),
        }
    else:
        record['kernel']['dtb_build_config_sha256'] = sha(ROOT / 'configs/kernel.config')
    (ROOT / 'records/boot-assets.json').write_text(json.dumps(record, indent=2) + '\n')
    print('PASS: eMMC/50MHz/8-bit DT, TF disabled, eMMC-only SPL, mmc0:1 extlinux, read-only identity, CRCs, shared inputs unchanged')


if __name__ == '__main__':
    main()
