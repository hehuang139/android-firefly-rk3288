# RK3399 ARM64 rkvdec / FFmpeg / Codec2

This is the new original Firefly-RK3399 bring-up profile. RK3288 runtime results
do not certify this board or these newly compiled libraries.

The fixed Linux 6.18.60 rkvdec driver supports H.264 and VP9. Its RK3399 Hantro
variant disables H.264. The Codec2 store registers `c2.firefly.h264.decoder` and
`c2.firefly.vp9.decoder`, with V4L2 Request required and CPU video fallback
rejected. The selected kernel does not provide an HEVC rkvdec path; no hardware
HEVC component is advertised. AC-3 and MP2 remain explicitly software audio.

The initial output path is linear 8-bit NV12 with 1920x1088 bounds. VP9 Profile 2,
HDR, 4K/8K throughput and secure playback are not advertised or validated.
VP9 Profile 0 is important for the official YouTube TV app, but codec registration
alone does not prove the app chose it or that frames were displayed correctly.

`build-ffmpeg.py` uses the pinned Kwiboo revision
`b57fbbe50c9b2656fad86a1a7eeabfd2b2a50935` plus the exact Android discovery patch.
It requires `--aosp`, `--out` (the isolated ARM64 build output), and `--work`.
Build the matching NDK sysroot and ARM64 CRT objects first. The script compiles
four libraries for `aarch64-linux-android37`, exports them under
`prebuilts/arm64`, and records new hashes. It never substitutes prior ARM32 blobs.

`firefly-vpu-probe` distinguishes H.264 and VP9 controls/request allocation.
`firefly-hwdecode sample.h264` and `firefly-hwdecode sample.ivf` require hardware
frames and hash visible decoded NV12 pixels. VP9 IVF uses its true packet lengths;
raw VP9 byte streams are not guessed. These are board tools, not offline proof
of actual decoding. Pixel comparisons, sustained Surface playback, audio sync
and official YouTube codec selection remain separate acceptance checks.

Derived Codec2 source retains the LineageOS notices and upstream revision in
`source-manifest.json`. Firmware and proprietary app licensing is handled
separately from these open video components.
