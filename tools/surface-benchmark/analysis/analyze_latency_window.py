# SPDX-License-Identifier: Apache-2.0
"""Analyze exact SF presentation intervals from a saved run folder or latency JSON."""
import argparse
import json
from pathlib import Path
from collect_surface_latency import event_stats, percentile, SENTINEL

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('input', type=Path)
p.add_argument('--layer-suffix', help='Optional override; otherwise select the newest nonempty layer')
p.add_argument('--output', type=Path)
p.add_argument('--fps', type=int, help='Default: delivery.json sourceFps, otherwise 60')
p.add_argument('--duration', type=float, help='Default: delivery.json durationUs, otherwise 12')
p.add_argument('--warmup', type=float, default=2)
a = p.parse_args()
source = a.input / 'latency.json' if a.input.is_dir() else a.input
output = a.output or Path(__file__).resolve().parent / (source.parent.name + '-steady-analysis.json')
delivery_path = source.parent / 'delivery.json'
delivery = json.loads(delivery_path.read_text(encoding='utf-8-sig')) if delivery_path.exists() else {}
a.fps = a.fps or delivery.get('sourceFps', 60)
a.duration = a.duration or delivery.get('durationUs', 12000000)/1e6
d = json.loads(source.read_text(encoding='utf-8-sig'))
by_layer = {}
for observation in d['observations']:
    name = observation['layer']
    if a.layer_suffix and not name.endswith(a.layer_suffix):
        continue
    # A newer snapshot can replace a not-yet-finalized row for the same desired
    # timestamp. Do not count both versions as different source frames.
    by_layer.setdefault(name, {}).update({r[0]: tuple(r) for r in observation['rows'] if r[0] > 0})
by_layer = {k: v for k, v in by_layer.items() if v}
if not by_layer:
    raise SystemExit('No nonempty matching layer found')
if a.layer_suffix and len(by_layer) != 1:
    raise SystemExit(f'Expected exactly one overridden layer, got {list(by_layer)}')
layer = max(by_layer, key=lambda key: min(by_layer[key]))
rows = sorted(by_layer[layer].values())
base = min(r[0] for r in rows if r[0] > 0)
expected = round(a.duration * a.fps)
grid_error_ns = max(abs((r[0]-base)-i*1e9/a.fps) for i, r in enumerate(rows))
complete = len(rows) == expected and grid_error_ns < 2000
warnings = []
if not complete:
    warnings.append('Full source timeline was not captured. Window origin uses the first '
                    'retained desired time and may not be the beginning of the clip; '
                    'do not treat this run as a verified 2-to-12-second measurement.')
whole_timestats = None
stats_path = source.parent / 'timestats.txt'
if stats_path.exists():
    import re
    raw = stats_path.read_text(encoding='utf-8-sig')
    matches = re.findall(r'layerName = ' + re.escape(layer) + r'\n.*?droppedFrames = (\d+)',
                         raw, re.DOTALL)
    if matches:
        whole_timestats = sum(map(int, matches))
        if whole_timestats != sum(r[2] == 0 for r in rows):
            warnings.append('Whole-layer TimeStats droppedFrames differs from zero-ready rows; '
                            'use zero-ready counts as observations, not confirmed drops.')
windows = []
for start, end in [(0, a.duration), (a.warmup, a.duration), (a.warmup, a.duration-2)] + \
                  [(i, min(i+1, a.duration)) for i in range(int(a.duration))]:
    rs = [r for r in rows if start <= (r[0]-base)/1e9 < end]
    ready = [r for r in rs if 0 < r[1] < SENTINEL and 0 < r[2] < SENTINEL]
    late = [(r[1]-r[0])/1e6 for r in ready]
    windows.append({'contentStartSeconds': start, 'contentEndSeconds': end,
                    'timelineRows': len(rs), 'positiveReadyRows': len(ready),
                    'zeroReadyRows': sum(r[2] == 0 for r in rs),
                    'inferredDroppedFrames': sum(r[2] == 0 for r in rs),
                    'inferredDropPercent': 100*sum(r[2] == 0 for r in rs)/len(rs) if rs else None,
                    'actualMinusDesiredP50Ms': percentile(late, .5),
                    'actualMinusDesiredP95Ms': percentile(late, .95),
                    **event_stats([r[1] for r in ready])})
report = {'inputFile': source.name, 'layer': layer,
          'selection': 'explicit suffix' if a.layer_suffix else 'newest first desired timestamp',
          'candidateLayers': list(by_layer),
          'firstDesiredTimestampNs': base,
          'sourceFps': a.fps, 'expectedSourceFrames': expected,
          'capturedSourceFrames': len(rows), 'maxSourceGridErrorNs': grid_error_ns,
          'fullSourceTimelineCaptured': complete,
          'wholeLayerTimeStatsDroppedFrames': whole_timestats,
          'warnings': warnings,
          'caveat': 'Windows use content time derived from first desired timestamp. '
                    'Ready-positive rows and unique actual events are not an explicit '
                    'Presented/Dropped-state export; compare TimeStats for drop counts.',
          'windows': windows}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'output': str(output.resolve()), 'layer': layer,
                  'fullSourceTimelineCaptured': complete, 'warnings': warnings,
                  'wholeLayerTimeStatsDroppedFrames': whole_timestats,
                  'steady': windows[1]}, indent=2))
