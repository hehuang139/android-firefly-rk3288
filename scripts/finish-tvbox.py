#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Sequential TV firmware build, assembly and verification with a durable status record."""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PORT = Path(__file__).resolve().parents[1]
ROOT = PORT.parent
ARTIFACTS = ROOT / 'tvbox-artifacts'
LOGS = ROOT / 'tvbox-logs'
STATUS = ARTIFACTS / 'build-status.json'
ARTIFACTS.mkdir(exist_ok=True)
lock = (ARTIFACTS / 'build.lock').open('w')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
state = {'status': 'running', 'pid': os.getpid(),
         'started_utc': datetime.now(timezone.utc).isoformat(), 'steps': []}


def save():
    ARTIFACTS.mkdir(exist_ok=True)
    temporary = STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    temporary.replace(STATUS)


def run(name, command, log=None):
    entry = {'name': name, 'started_utc': datetime.now(timezone.utc).isoformat()}
    state['steps'].append(entry)
    state['current_step'] = name
    save()
    print(name, flush=True)
    log_path = LOGS / (log or (name + '.log'))
    with log_path.open('w') as output:
        result = subprocess.run(list(map(str, command)), cwd=ROOT,
                                stdout=output, stderr=subprocess.STDOUT)
    entry.update({'exit_code': result.returncode, 'log': str(log_path.relative_to(ROOT)),
                  'finished_utc': datetime.now(timezone.utc).isoformat()})
    save()
    if result.returncode:
        raise RuntimeError(name + ' failed; see ' + str(log_path))


def build_inputs():
    """Fingerprint product inputs, including data and prebuilts, before building."""
    inputs = {}
    for directory in ['device/firefly/rk3288', 'graphics']:
        for path in sorted((PORT / directory).rglob('*')):
            if path.is_file():
                inputs[str(path.relative_to(PORT))] = file_digest(path)
    return inputs


def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as payload:
        for block in iter(lambda: payload.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


try:
    LOGS.mkdir(exist_ok=True)
    raise RuntimeError('Historical full-media release pipeline. Follow BUILD.md for the public source profile; its clean image validation is pending.')
    inputs = build_inputs()
    (ARTIFACTS / 'build-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    state['input_manifest'] = 'tvbox-artifacts/build-inputs.json'
    run('install-tv', [PORT / 'build.sh', 'install'])
    build_number = 1
    while (LOGS / f'build-tv-{build_number:02}.log').exists():
        build_number += 1
    state['build_log'] = f'tvbox-logs/build-tv-{build_number:02}.log'
    run('build-tv', [PORT / 'build.sh', 'build'], f'build-tv-{build_number:02}.log')
    if build_inputs() != inputs:
        raise RuntimeError('Product sources changed during the build; reinstall and rebuild before packaging')
    run('verify-tv-features', [sys.executable, PORT / 'scripts/verify-tv-features.py',
        '--aosp', ROOT / 'aosp', '--report', ARTIFACTS / 'tv-feature-validation.json'])
    run('verify-media', [sys.executable, PORT / 'scripts/verify-tv-media.py',
        '--aosp', ROOT / 'aosp', '--include-audio', '--include-remote',
        '--report', ARTIFACTS / 'tv-vendor-elf-validation.json'])
    for action in ['image', 'verify', 'image-emmc', 'verify-emmc']:
        run(action, [PORT / 'build.sh', action])
    images = [ARTIFACTS / ('firefly-rk3288-tv-android17-' + medium + '-alpha.img')
              for medium in ['sd', 'emmc']]
    for image in images:
        run('compress-' + image.stem, ['xz', '-T2', '-3', '--keep', '--force', image])
        run('check-xz-' + image.stem, ['xz', '-t', str(image) + '.xz'])
    source_archive = ARTIFACTS / 'firefly-rk3288-tv-source.tar.gz'
    with tempfile.TemporaryDirectory(prefix='.tv-source-', dir=ARTIFACTS) as temporary:
        staged_archive = Path(temporary) / source_archive.name
        run('archive-tv-source', [sys.executable, PORT / 'scripts/package-source.py',
                                  '--include-prebuilts', '--output', staged_archive])
        staged_archive.replace(source_archive)
    files = images + [Path(str(x) + '.xz') for x in images]
    files += [source_archive]
    files += sorted(ARTIFACTS.glob('*.apk'))
    with (ARTIFACTS / 'SHA256SUMS').open('w') as sums:
        for path in files:
            digest = file_digest(path)
            sums.write(digest + '  ' + path.name + '\n')
    state['status'] = 'complete'
    state['finished_utc'] = datetime.now(timezone.utc).isoformat()
except Exception as error:
    state['status'] = 'failed'
    state['error'] = str(error)
    print(error, file=sys.stderr, flush=True)
finally:
    save()
raise SystemExit(state['status'] != 'complete')
