#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Install RK3399 into a separate AOSP checkout/overlay, preserving RK3288."""
import argparse
import importlib.util
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('aosp', type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    aosp = args.aosp.resolve()
    board = source / 'device/firefly/rk3399'
    dest = aosp / 'device/firefly/rk3399'
    if not (aosp / '.repo/manifest.xml').is_file():
        parser.error('AOSP checkout metadata is missing')
    if (aosp / 'device/firefly/rk3288').exists():
        parser.error('RK3288 device is visible: use a separate checkout or mask it in the isolated overlay')
    if dest.exists() and not (dest / '.firefly-port').is_file():
        parser.error('Refusing to overwrite an unmanaged RK3399 device directory')
    for required in (board, source / 'graphics/rk3399'):
        if not required.is_dir():
            parser.error(f'Missing source input: {required}')
    spec = importlib.util.spec_from_file_location('firefly_common_installer', source / 'scripts/install-port.py')
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    common.apply_adbd_patch(aosp, source)
    common.apply_soong_patch(aosp, source)
    common.apply_hosts_patch(aosp, source)
    if (aosp / 'system/core/rootdir/etc/hosts').read_bytes() != (board / 'adblock/hosts').read_bytes():
        parser.error('RK3399 hosts list differs from the checked release patch')
    common.apply_release_patch(aosp, source, 'external/minigbm',
        'cros_gralloc/cros_gralloc_driver.cc',
        'minigbm/0001-release-drm-master-and-allow-nv12-textures.patch',
        'ce79bbee67b3e2ea7abb110e1415e9ceceaa6471',
        '98e9054d5f98c3d107c25be6ac240c0b4bb858717860657641479595d3ec3103',
        '5ae73cb63c984d75f96582c71065c6e90eafd0c67a774462bfbe1d0451734a71')
    common.apply_tvsettings_patches(aosp, source)
    # The old ARM32 NetBpfLoad workaround is intentionally not applied to ARM64.
    dest.mkdir(parents=True, exist_ok=True)
    (dest / '.firefly-port').write_text('Managed by isolated Firefly-RK3399 Android port\n')
    shutil.copytree(board, dest, dirs_exist_ok=True, copy_function=common.copy_build_input)
    shutil.copytree(source / 'graphics', dest / 'graphics', dirs_exist_ok=True,
                    copy_function=common.copy_build_input)
    for name in ('BoardConfigGraphics.mk', 'graphics.mk'):
        common.copy_build_input(source / 'graphics/rk3399' / name, dest / 'graphics' / name)
    print(f'Installed RK3399 sources: {dest}; no RK3288 tree was modified')


if __name__ == '__main__':
    main()
