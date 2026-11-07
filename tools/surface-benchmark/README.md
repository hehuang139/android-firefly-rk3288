# Real Surface H.264 benchmark

This test forces `c2.firefly.h264.decoder`, feeds local AVC asynchronously,
and presents to a real SurfaceView. It uses no audio, network, software
fallback, or per-pixel hashing on the playback thread. It does not stop
other applications or alter device settings.

## Build

The Activity and manifest are the sources used for the validated v1.1 APK;
only license comments have been added. The `Android.bp` is a new portable
build entry and has not yet been rebuilt as part of a full AOSP product.
The original diagnostic build used javac 17 bytecode, d8, aapt2 and signapk
from the already built AOSP tree. It produced an 18,018,680-byte APK with
SHA-256 `6f8abc9a8519a198a66ad41b2fbd90433d60fa35f9385171c709487e870c9636`.

1. Place this directory within the complete AOSP source tree.
2. Run `bash make-samples.sh` with host FFmpeg/libx264, ffprobe and sha256sum.
   The two assets are 12-second 1920x1080 AVC High, 8-bit, with B frames:
   30 FPS/level 4.1/360 frames and 60 FPS/level 4.2/720 frames.
3. Select the port's ARM32 product with its normal envsetup/lunch procedure.
4. Build `m FireflySurfaceBenchmark`. No platform/private APIs are used.
   Assets must remain uncompressed because the test opens them by FD.
5. Locate the resulting APK in product output; it is signed by the AOSP
   test key and needs no privileged permissions.

`fixtures/` preserves historical sample metadata and hashes. Newly generated
samples may differ across FFmpeg/x264 versions; generated results are saved
under `generated-fixture-info/`, so historical hashes are not overwritten.
For an exact historical A/B comparison, use assets matching the historical
hashes. Assets and prebuilt APKs are omitted from this minimal source export.

## Run

Use the intended device serial in place of `DEVICE_SERIAL`. Stop competing
video playback and confirm there is no other active hardware decoder before
measuring. The benchmark never does this on behalf of the user.

```sh
adb -s DEVICE_SERIAL install -r FireflySurfaceBenchmark.apk
adb -s DEVICE_SERIAL shell am start -S -W \
  -n org.firefly.surfacebench/.BenchmarkActivity \
  --ei fps 60 --ez paced true --ez drop_late false --ei warmup_ms 2000
adb -s DEVICE_SERIAL shell run-as org.firefly.surfacebench \
  cat files/surface-60-paced-nodrop.json
```

A normal paced run takes roughly 14 seconds, with a 60-second failure
deadline. Wait until its result is visible before reading JSON. Use `fps 30`
and `surface-30-paced-nodrop.json` for the control run. `-S` stops only the
benchmark package. Surface destruction terminates measurement with an
error instead of reporting successful completion.

The clock is anchored once, 250 ms after the first decoded output. The
first two seconds are excluded from steady delivery statistics; it does
not repeatedly reanchor to hide late frames. Optional `drop_late=true`
explicitly discards outputs later than max(one source frame, 50 ms), and
records these separately. Optional `paced=false` measures delivery into a
Surface without pacing, still subject to buffer-queue backpressure; it is
not pure VPU throughput.

## Measure actual presentation separately

On this firmware, `media_native/render_metrics_enabled=false` makes the
MediaCodec rendered callback echo the requested time immediately. The
fields `steadyRenderedCallbackFps`, render lateness and rendered callback
counts therefore cannot prove actual HDMI presentation. `completedWithoutError`
also means only that the API run completed, not that it met its FPS target.

Run the collector in another terminal **before** starting the benchmark:

```sh
python3 analysis/collect_surface_latency.py --adb /path/to/adb \
  --serial DEVICE_SERIAL --seconds 20 --output run/latency.json
```

It calls only SurfaceFlinger `--list` and `--latency`, selects exact BLAST
layers, and stores raw desired/actual/ready timestamps. It does not start
applications, clear statistics or change flags. The serial is required
explicitly and is not stored in the report. adb errors may contain host
details; inspect errors before publishing a report.

Save the app JSON as `run/delivery.json`. If explicit dropped-frame counts
are required, separately enable TimeStats before playback and dump it after:

```sh
adb -s DEVICE_SERIAL shell dumpsys SurfaceFlinger --timestats -clear -enable
# Play the local sample, then:
adb -s DEVICE_SERIAL shell dumpsys SurfaceFlinger --timestats -disable -dump \
  > run/timestats.txt
python3 analysis/analyze_latency_window.py run --output run/steady-analysis.json
```

These TimeStats commands alter diagnostic state and are not part of the
read-only collector. Windows PowerShell users should save text as UTF-8;
the analyzer accepts UTF-8 with or without BOM.

The analyzer verifies the complete expected 720/360 desired-time grid,
selects the newest nonempty layer, and replaces duplicate/pending snapshots
by desired timestamp. It reports full, 2–12 and 2–10 second windows. A partial
capture emits a warning; do not treat that run as a complete steady window.

SurfaceFlinger latency rows lack explicit Presented/Dropped state. Positive
ready rows and deduplicated actual events are useful observations, and
zero-ready counts should be cross-checked against TimeStats `droppedFrames`.
TimeStats averageFPS is based on a millisecond histogram and can overstate
FPS; use the raw nanosecond intervals. Physical refresh should separately
be verified with DRM vblank and the active clock tree.

## Format limits

Version 1.1 omits optional explicit profile/level requests when configuring
the decoder; the original CSD/SPS, resolution and frame rate are unchanged.
The firmware advertised level 4.1, so the first test's explicit level 4.2
request was rejected before input was queued. Forced-path success does not
change the advertised codec capability or prove arbitrary 1080p60 support.

The baseline measured 720 correct hardware-decoded frames, 6 whole-run
TimeStats drops, 597/600 in the 2–12 second window (~59.58 FPS), and 480/480
in the middle 8 seconds (60 FPS). The 30 FPS sample recorded no drops.
These local results do not establish flawless real YouTube playback.

License: Apache-2.0; see the export's `licenses/Apache-2.0.txt`.
