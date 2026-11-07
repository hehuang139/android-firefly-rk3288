# RK3288 playback source export

This export contains the final playback changes and small diagnostic sources.
It is an integration payload for the complete Firefly device port, not a
standalone Android distribution. No overlay candidate or device/user data is
included. `source-manifest.json` records provenance, target paths and hashes.

## Apply to the pinned sources

1. Check out Android minigbm commit
   `ce79bbee67b3e2ea7abb110e1415e9ceceaa6471`. From its project root, apply
   `patches/minigbm/0001-release-drm-master-and-allow-nv12-textures.patch`.
   This cumulative patch includes both the earlier DRM-master release and
   the NV12 video-texture fallback. Do not apply the old incremental patches
   again. The manifest records the exact base and expected result file hashes.
   Preserve LF line endings when comparing hashes; the independent Windows
   check used `git -c core.autocrlf=false apply`.
2. Overlay `device/firefly/rk3288/media/codec2/` on the complete device port.
   Keep its headers, component interface/store, Android.bp, codec XML,
   VINTF, seccomp and ueventd configuration. These two files alone do not
   form a buildable codec service.
3. Use the complete cumulative kernel patch, final config and DTS under
   `kernel/final/`. The small v2 DMA patch under `patches/kernel/` is already
   included and is retained for review; do not apply it twice. Follow the
   repository BUILD.md for the authoritative integration sequence.
4. Use the final `device/firefly/rk3288/init/init.fireflyrk3288.rc`, or apply
   the SF-only patch to the exact pre-SF rc identified in the manifest.
   Both include explicit early/earlyGl app durations. Preserve the rest of
   the device's working audio and service configuration when integrating.
5. Integrate the separate native-1600x900 NPLL=216 MHz DT source change from
   the full port. It is required for this monitor's exact 108 MHz pixel
   clock; the DT binary and private patching tool are intentionally not
   included here. Validate other PLL consumers and physical vblank after boot.

The selected HWC is the original CLIENT composition service. The experimental
overlay route was withdrawn from the final configuration because color
conversion had not been validated on original RK3288 VOP 3.1. Do not enable
overlay defaults based on this export.

## Build dependencies

- The complete ARM32 AOSP target and its pinned sources/toolchain, including
  minigbm, libdrm, Codec2 headers and the device media Android.bp.
- The complete FFmpeg V4L2 Request source at
  `b57fbbe50c9b2656fad86a1a7eeabfd2b2a50935` from
  <https://github.com/Kwiboo/FFmpeg>, plus the port's Android discovery/UAPI
  patch and `build-ffmpeg.py`. The minimal service uses avcodec, avutil and
  swscale; include actual configure options and corresponding source.
- The Codec2 bridge originates from
  <https://github.com/LineageOS/android_external_ffmpeg_codec2> at
  `00f6f65c7ef381470efbcfca8c0316bdcdfcffe7`.
- Kernel cross compiler, full source and config matching the port's Linux
  6.18.60 build. Publishing the zImage requires the corresponding source,
  config and full patch set, not just the small reference fix in this export.
- Python 3.9+ and adb for the optional analysis tools; FFmpeg with libx264
  and ffprobe for the generated local test samples.

The historical production artifacts were compiled and tested. This export
does not repeat the complete clean product build. The portable benchmark
module is supplied separately with its validation status in its README.

## Validated outcome and limits

H.264 hardware pixel hashes match the golden references for the tested 720p,
1080p30 and 720-frame 1080p60 streams. Local Surface playback achieved
480/480 presented timeline events in the middle 8 seconds of the 60 FPS
sample; the 2–12 second window had 597/600, approximately 59.58 FPS. The
30 FPS sample had no recorded drops. These results do not establish flawless
YouTube playback: actual SmartTube still showed a residual 30/60 render-rate
policy issue and was deferred at the user's request. H.265 hardware decode
remains disabled; VP9/AV1 hardware decode and smooth 4K/8K playback are not
validated. No minimum-refresh-rate override is part of this export.

## Licensing

- minigbm: BSD-3-Clause; original copyright retained, complete license in
  `licenses/BSD-3-Clause-minigbm.txt`.
- Codec2 wrappers, device init and the new test tools: Apache-2.0. Existing
  third-party copyright notices remain in their source files.
- Modified Hantro kernel files: GPL-2.0 as declared upstream; keep kernel
  copyright headers and the corresponding source. The upstream license text
  is included under `licenses/GPL-2.0.txt`.
- FFmpeg: LGPL-2.1-or-later for the stated minimal configuration, subject to
  actual build options and individual source notices. The wrapper's Apache
  license does not relicense FFmpeg. See `licenses/ffmpeg-LICENSE.md` and
  `licenses/LGPL-2.1.txt`.

The code has mixed upstream licenses. A repository-wide license must not
replace those per-component obligations. Host FFmpeg/libx264 binaries are
build tools and are not included in this export.
