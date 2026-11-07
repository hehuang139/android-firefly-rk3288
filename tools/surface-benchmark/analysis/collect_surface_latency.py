# SPDX-License-Identifier: Apache-2.0
"""Read-only SurfaceFlinger latency collector; never starts or changes apps."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parent
DEFAULT_ADB = 'adb'
SENTINEL = 2**63 - 1


def adb_shell(adb, serial, command):
    result = subprocess.run([adb, '-s', serial, 'shell', command],
                            capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def shell_quote(value):
    return "'" + value.replace("'", "'\\''") + "'"


def layer_names(text, match):
    names = []
    for line in text.splitlines():
        if match not in line or '(BLAST)' not in line:
            continue
        if line.startswith('RequestedLayerState{'):
            name = line[len('RequestedLayerState{'):]
            name = re.split(r' (?:parentId|relativeParentId|z)=', name)[0]
            name = name.removesuffix('}')
        else:
            name = line.strip()
        names.append(name)
    return names


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    idx = (len(ordered) - 1) * fraction
    lo = int(idx)
    return ordered[lo] + (ordered[min(lo + 1, len(ordered) - 1)] - ordered[lo]) * (idx - lo)


def event_stats(timestamps):
    ts = sorted(set(timestamps))
    gaps = [(b-a)/1e6 for a, b in zip(ts, ts[1:])]
    elapsed = (ts[-1]-ts[0])/1e9 if len(ts) > 1 else 0
    return {'distinctActualEvents': len(ts),
            'firstActualTimestampNs': ts[0] if ts else None,
            'lastActualTimestampNs': ts[-1] if ts else None,
            'elapsedSeconds': elapsed,
            'actualTimelineEventsPerSecond': (len(ts)-1)/elapsed if elapsed else None,
            'intervalMedianMs': statistics.median(gaps) if gaps else None,
            'intervalP95Ms': percentile(gaps, .95),
            'intervalMaxMs': max(gaps) if gaps else None,
            'intervalsOver25ms': sum(v > 25 for v in gaps),
            'intervalsOver50ms': sum(v > 50 for v in gaps)}


def summarize(observations):
    layers = {}
    for observation in observations:
        layer = observation['layer']
        layers.setdefault(layer, set()).update(tuple(row) for row in observation['rows'])
    summary = {}
    for layer, rows in layers.items():
        valid = [r for r in rows if 0 < r[1] < SENTINEL]
        ready = [r for r in valid if 0 < r[2] < SENTINEL]
        summary[layer] = {
            'uniqueRows': len(rows), 'validActualRows': len(valid),
            'invalidOrPendingActualRows': len(rows)-len(valid),
            'rowsWithPositiveReadyTimestamp': len(ready),
            'duplicateActualRows': len(valid)-len({r[1] for r in valid}),
            'allValidActual': event_stats([r[1] for r in valid]),
            'positiveReadyActual': event_stats([r[1] for r in ready]),
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', default=str(DEFAULT_ADB))
    parser.add_argument('--serial', required=True, help='Explicit adb target; not stored in output')
    parser.add_argument('--match', default='org.firefly.surfacebench')
    parser.add_argument('--seconds', type=float, default=0)
    parser.add_argument('--interval', type=float, default=0.5)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.seconds < 0 or args.interval < .1:
        parser.error('seconds must be nonnegative; interval must be at least 0.1')
    started = time.monotonic()
    report = {'startedUtc': datetime.now(timezone.utc).isoformat(),
              'match': args.match,
              'caveat': 'Latency rows lack Presented/Dropped state. Distinct actual '
                        'timestamps are presentation-timeline events, not proof of '
                        'unique visible video frames. Snapshot retention is finite.',
              'observations': [], 'errors': []}
    while True:
        try:
            listing = adb_shell(args.adb, args.serial, 'dumpsys SurfaceFlinger --list')
            for layer in layer_names(listing, args.match):
                raw = adb_shell(args.adb, args.serial,
                                'dumpsys SurfaceFlinger --latency ' + shell_quote(layer))
                lines = raw.splitlines()
                rows = [list(map(int, line.split())) for line in lines
                        if re.fullmatch(r'\s*-?\d+\s+-?\d+\s+-?\d+\s*', line)]
                report['observations'].append({
                    'elapsedSeconds': time.monotonic()-started, 'layer': layer,
                    'refreshPeriodNs': int(lines[0]) if lines and lines[0].isdigit() else None,
                    'rows': rows})
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            report['errors'].append({'elapsedSeconds': time.monotonic()-started,
                                     'message': str(error)})
        if time.monotonic()-started >= args.seconds:
            break
        time.sleep(min(args.interval, max(0, args.seconds-(time.monotonic()-started))))
    report['elapsedSeconds'] = time.monotonic()-started
    report['summary'] = summarize(report['observations'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(args.output.resolve()), 'summary': report['summary'],
                      'errors': report['errors']}, indent=2))


if __name__ == '__main__':
    main()
