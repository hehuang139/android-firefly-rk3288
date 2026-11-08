#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package a pinned Rockchip RK3399 USB RAM loader without accessing a device."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import struct
import subprocess
import urllib.request


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path, help='New private staging directory')
    a = p.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        p.error('The pinned official packaging tool requires Linux x86_64')
    if a.output.exists():
        p.error('Use a new output directory; no existing files are replaced')
    a.output.mkdir(parents=True)
    root = a.output.resolve()
    source = json.loads(Path(__file__).with_name('usb-loader-sources.json').read_text())
    for name, entry in source['files'].items():
        request = urllib.request.Request(entry['url'], headers={'User-Agent': 'Firefly-RK3399-source-build/1'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(entry['bytes'] + 1)
        if len(data) != entry['bytes'] or digest(data) != entry['sha256']:
            raise ValueError('Pinned source mismatch: ' + name)
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    tool = root / 'tools/boot_merger'
    raw = tool.read_bytes()
    if raw[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', raw, 18)[0] != 62:
        raise ValueError('Packaging tool is not the expected x86_64 ELF')
    tool.chmod(0o755)
    subprocess.run([str(tool), 'RKBOOT/RK3399MINIALL.ini'], cwd=root, check=True)
    artifact = root / 'rk3399_loader_v1.30.130.bin'
    data = artifact.read_bytes()
    if data[:4] != b'BOOT':
        raise ValueError('Missing Rockchip loader package header')
    source.update(status='PACKAGED_OFFLINE_NOT_DOWNLOADED_TO_BOARD',
                  artifact={'name': artifact.name, 'bytes': len(data), 'sha256': digest(data)},
                  flash_write_performed=False,
                  purpose='RK3399 MaskROM USB RAM DDR/usbplug download candidate',
                  board_validation='Original Firefly-RK3399 DDR3 not yet tested')
    (root / 'usb-loader-manifest.json').write_text(json.dumps(source, indent=2) + '\n')
    print(json.dumps(source['artifact']))


if __name__ == '__main__':
    main()
