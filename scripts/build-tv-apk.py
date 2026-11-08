#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a standalone platform-signed TV launcher with existing AOSP host tools.

The complete firmware continues to use the ordinary Soong android_app module.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--aosp', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--report', type=Path, required=True)
args = parser.parse_args()
aosp = args.aosp.resolve()
port = Path(__file__).resolve().parents[1]
source = port / 'device/firefly/rk3288/tv'
jdk = aosp / 'prebuilts/jdk/jdk21/linux-x86/bin'
host = aosp / 'out/host/linux-x86'
sdk = aosp / 'prebuilts/sdk/37.0/public/android.jar'
framework = aosp / 'out/soong/.intermediates/frameworks/base/framework/android_common/turbine-combined/framework.jar'
checks = []


def run(name, command):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    checks.append({'name': name, 'exit_code': result.returncode,
                   'output': result.stdout + result.stderr})
    if result.returncode:
        raise RuntimeError(name + ': ' + result.stderr)


args.output = args.output.resolve()
args.output.parent.mkdir(parents=True, exist_ok=True)
try:
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        classes = work / 'classes'
        classes.mkdir()
        aidl = port / 'device/firefly/rk3288/remote/aidl'
        run('aidl_java', [host / 'bin/aidl', '--lang=java', '--structured', '--stability=vintf',
            '--version=1', '--hash=' + (aidl / 'aidl_api/vendor.firefly.hardware.remote/1/.hash').read_text().strip(),
            '--out=' + str(work / 'aidl'), '-I' + str(aidl),
            aidl / 'vendor/firefly/hardware/remote/IRemote.aidl'])
        sources = sorted((source / 'src').rglob('*.java')) + sorted((work / 'aidl').rglob('*.java'))
        run('javac_sdk37_platform', [jdk / 'javac', '--release', '17', '-cp',
            str(framework) + ':' + str(sdk), '-d', classes, *sources])
        run('classes_jar', [jdk / 'jar', '--create', '--file', work / 'classes.jar',
                           '-C', classes, '.'])
        run('dex', [jdk / 'java', '-cp', host / 'framework/d8.jar', 'com.android.tools.r8.D8',
                    '--release', '--min-api', '28', '--lib', sdk,
                    '--output', work / 'dex.zip', work / 'classes.jar'])
        run('resources_compile', [host / 'bin/aapt2', 'compile', '--dir', source / 'res',
                                  '-o', work / 'resources.zip'])
        run('resources_link', [host / 'bin/aapt2', 'link', '-I',
            aosp / 'out/target/product/rk3288/system/framework/framework-res.apk',
            '--manifest', source / 'AndroidManifest.xml', '-o', work / 'unsigned.apk',
            work / 'resources.zip'])
        with zipfile.ZipFile(work / 'unsigned.apk', 'a') as apk, zipfile.ZipFile(work / 'dex.zip') as dex:
            for item in dex.infolist():
                apk.writestr(item, dex.read(item))
            for asset in sorted((source / 'assets').rglob('*')):
                if asset.is_file():
                    apk.write(asset, 'assets/' + asset.relative_to(source / 'assets').as_posix())
        run('zipalign', [aosp / 'prebuilts/build-tools/linux-x86/bin/zipalign',
                         '-f', '4', work / 'unsigned.apk', work / 'aligned.apk'])
        keys = aosp / 'build/target/product/security'
        run('platform_sign', [jdk / 'java', '-Djava.library.path=' + str(host / 'lib64'),
            '-jar', host / 'framework/signapk.jar', keys / 'platform.x509.pem',
            keys / 'platform.pk8', work / 'aligned.apk', args.output])
        run('verify_signature', [jdk / 'java', '-jar', aosp / 'prebuilts/sdk/tools/linux/lib/apksigner.jar',
            'verify', '--verbose', '--print-certs', args.output])
        run('manifest_badging', [host / 'bin/aapt2', 'dump', 'badging', args.output])
    passed = True
except Exception as error:
    checks.append({'name': 'completion', 'exit_code': 1, 'output': str(error)})
    passed = False
report = {'scope': 'Standalone launcher APK build using AOSP SDK 37/platform headers and platform key',
          'passed': passed, 'checks': checks,
          'source_sha256': {str(p.relative_to(port)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(source.rglob('*')) if p.is_file()}}
if passed:
    report.update({'output': str(args.output), 'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                   'bytes': args.output.stat().st_size})
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': passed, 'report': str(args.report)}))
raise SystemExit(not passed)
