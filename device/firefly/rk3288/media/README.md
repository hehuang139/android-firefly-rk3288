# Hantro H.264 / FFmpeg / Codec2

The `fix/live-channel-audio` branch adds AC-3/MP2 software-audio decoding.
The paired ARM32 components have been installed and exercised on the board:
specified-codec PCM probes reached EOS and selected live channels played in the
native TV activity. The later AVC metadata-level update retains the original
1920x1088 picture-size limit; it does not establish full Level 5.1 capabilities.
See [candidate build and validation](../../../../docs/live-channel-audio-candidate.md).
The H.264 results below describe the accepted `main` baseline.

The final tested hardware path is H.264 through Linux V4L2 Request and the
`c2.firefly.h264.decoder` bridge. It requires the cumulative kernel/config in
kernel/final, the pinned FFmpeg source and Android discovery patch, the final
Codec2 source, minigbm NV12 fix, and the SF timing configuration together.
Custom HEVC and its MMU remain disabled in the final DTS. Retained HEVC source
is experimental; its presence does not establish usable H.265 hardware decode.
VP9/AV1 hardware decode and 4K/8K playback are not validated.

`build-ffmpeg.py` fetches Kwiboo/FFmpeg at
`b57fbbe50c9b2656fad86a1a7eeabfd2b2a50935`, verifies and applies the local patch,
and, on this candidate branch, builds avcodec, avutil, swscale and swresample
with the AOSP ARM32 Clang/sysroot/CRT. It enables only AC-3 and MP2 in addition
to the existing H.264/HEVC decoder selection; the corresponding parsers are
`ac3` and `mpegaudio`. The added codecs are software audio decoders and do not
establish new video hardware capabilities.
It installs shared libraries into media/prebuilts/arm and records hashes in
source-manifest.json. The public repository does not contain those binaries.
The build also generates the required `include/libswresample/` headers; run it
before resolving the candidate Soong graph. The manifest preserves the accepted
baseline hashes separately from the isolated candidate payload hashes.
The complete adapted Codec2 module derives from LineageOS revision
`00f6f65c7ef381470efbcfca8c0316bdcdfcffe7`; notices are retained.

See the root BUILD.md for order/dependencies, docs/playback-sources.md for
measured playback results and limits, and THIRD_PARTY.md for licenses.
Both initial probing and actual decoded-pixel/Surface measurements are needed:
a visible `/dev/video*` or registered codec alone is not a decode pass.
