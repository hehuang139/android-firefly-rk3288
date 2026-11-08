#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the production EOS recovery policy on a JVM; this does not emulate MediaPlayer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--jdk', type=Path, required=True)
parser.add_argument('--report', type=Path, required=True)
args = parser.parse_args()
port = Path(__file__).resolve().parents[1]
inputs = [port / 'device/firefly/rk3288/tv/src/org/firefly/tv/LiveReconnectPolicy.java',
          port / 'tests/LiveReconnectHostTest.java']
suffix = '.exe' if os.name == 'nt' else ''
with tempfile.TemporaryDirectory() as directory:
    classes = Path(directory) / 'classes'
    compiled = subprocess.run([str(args.jdk / ('bin/javac' + suffix)), '--release', '17',
        '-encoding', 'UTF-8', '-d', str(classes), *map(str, inputs)], capture_output=True, text=True)
    executed = None
    if compiled.returncode == 0:
        executed = subprocess.run([str(args.jdk / ('bin/java' + suffix)), '-ea', '-cp', str(classes),
            'org.firefly.tv.LiveReconnectHostTest'], capture_output=True, text=True)
    report = {
        'scope': 'Production clean-EOS recovery policy. MediaPlayer callbacks, delayed Handler generation checks, and device playback require separate integration verification.',
        'compile_exit': compiled.returncode, 'compile_output': compiled.stdout + compiled.stderr,
        'run_exit': None if executed is None else executed.returncode,
        'run_output': '' if executed is None else executed.stdout + executed.stderr,
        'passed': executed is not None and executed.returncode == 0,
        'inputs': {str(path.relative_to(port)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
    }
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
raise SystemExit(not report['passed'])
