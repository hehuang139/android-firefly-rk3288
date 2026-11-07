#!/usr/bin/env python3
"""Check the real compiled assets with both shared media contract readers."""
# SPDX-License-Identifier: MIT
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def main():
    assembler = module('firefly_assemble_emmc', PORT / 'scripts/assemble-sd.py')
    verifier = module('firefly_verify_emmc', PORT / 'scripts/verify-sd.py')
    audit = verifier.Audit('compiled-eMMC-boot-assets')
    dtb = ROOT / 'boot/rk3288-firefly-android.dtb'
    config = ROOT / 'boot/extlinux.conf'
    idb = ROOT / 'bootloader/idbloader.img'
    uboot = ROOT / 'bootloader/u-boot-dtb.img'
    with tempfile.TemporaryDirectory(prefix='firefly-emmc-contract-') as directory:
        scratch = Path(directory)
        (scratch / 'boot').mkdir(); (scratch / 'extlinux').mkdir()
        shutil.copyfile(dtb, scratch / 'boot/rk3288-firefly-android.dtb')
        shutil.copyfile(config, scratch / 'extlinux/extlinux.conf')
        assembler.check_boot_medium_files(scratch, 'emmc')
        assembler.check_boot_medium_loaders(idb, uboot, 'emmc')
        audit.check('assembler-media-files-and-loaders', True)
        verifier.check_boot_medium_files(dtb, config.read_text(), 'emmc', audit)
        verifier.check_boot_medium_loaders(idb.read_bytes(), uboot.read_bytes(), 'emmc', audit, scratch)
    audit.finish('passed')
    paths = [dtb, config, idb, uboot, PORT / 'scripts/assemble-sd.py', PORT / 'scripts/verify-sd.py']
    audit.data['inputs'] = {str(path.relative_to(PORT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    (ROOT / 'records/media-contract-validation.json').write_text(json.dumps(audit.data, indent=2) + '\n')
    print('PASS: shared assembler and verifier accepted the actual eMMC DTB/extlinux/idbloader/U-Boot')


if __name__ == '__main__':
    main()
