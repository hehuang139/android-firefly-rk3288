#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check installed product files for the TV/parental/adblock feature payload."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--aosp', type=Path, required=True)
parser.add_argument('--report', type=Path, required=True)
args = parser.parse_args()
port = Path(__file__).resolve().parents[1]
device = port / 'device/firefly/rk3288'
product = args.aosp / 'out/target/product/rk3288'
checks = []
for source, destination in [
    ('tv-data/channels.json', 'product/etc/firefly-tv/channels.json'),
    ('tv-data/channels.m3u', 'product/etc/firefly-tv/channels.m3u'),
    ('tv-data/epg.xml', 'product/etc/firefly-tv/epg.xml'),
    ('tv-data/epg-settings.json', 'product/etc/firefly-tv/epg-settings.json'),
    ('adblock/hosts', 'system/etc/hosts'),
    ('adblock/cmfa-rules.yaml', 'product/etc/firefly-tv/adblock/cmfa-rules.yaml'),
    ('kids-content/colors.mp4', 'product/etc/firefly-tv/kids/colors.mp4'),
    ('kids-content/counting.mp4', 'product/etc/firefly-tv/kids/counting.mp4'),
    ('tv/privapp-permissions-firefly-tv.xml', 'system_ext/etc/permissions/privapp-permissions-firefly-tv.xml'),
]:
    original, installed = device / source, product / destination
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    checks.append({'name': destination, 'passed': installed.is_file() and digest(original) == digest(installed),
                   'source_sha256': digest(original), 'installed_sha256': digest(installed)})
apk = product / 'system_ext/priv-app/FireflyTV/FireflyTV.apk'
if apk.is_file():
    result = subprocess.run([str(args.aosp / 'out/host/linux-x86/bin/aapt2'), 'dump',
                             'xmltree', '--file', 'AndroidManifest.xml', str(apk)],
                            capture_output=True, text=True)
    for value in ['KidsActivity', 'ParentalActivity', 'PuzzleActivity', 'WatchTimeTracker',
                  'ParentalBootReceiver', 'android.permission.FORCE_STOP_PACKAGES']:
        checks.append({'name': 'manifest_' + value, 'passed': result.returncode == 0 and value in result.stdout})
else:
    checks.append({'name': 'launcher_apk_exists', 'passed': False})
report = {'scope': 'Installed TV product feature payload and launcher manifest',
          'passed': all(x['passed'] for x in checks), 'checks': checks}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
raise SystemExit(not report['passed'])
