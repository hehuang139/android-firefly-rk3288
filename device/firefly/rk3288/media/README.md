# Hantro H.264 / FFmpeg / Codec2

The final tested hardware path is H.264 through Linux V4L2 Request and the
`c2.firefly.h264.decoder` bridge. It requires the cumulative kernel/config in
kernel/final, the pinned FFmpeg source and Android discovery patch, the final
Codec2 source, minigbm NV12 fix, and the SF timing configuration together.
Custom HEVC and its MMU remain disabled in the final DTS. Retained HEVC source
is experimental; its presence does not establish usable H.265 hardware decode.
VP9/AV1 hardware decode and 4K/8K playback are not validated.

`build-ffmpeg.py` fetches Kwiboo/FFmpeg at
`b57fbbe50c9b2656fad86a1a7eeabfd2b2a50935`, verifies and applies the local patch,
and builds avcodec, avutil and swscale with the AOSP ARM32 Clang/sysroot/CRT.
It installs shared libraries into media/prebuilts/arm and records hashes in
source-manifest.json. The public repository does not contain those binaries.
The complete adapted Codec2 module derives from LineageOS revision
`00f6f65c7ef381470efbcfca8c0316bdcdfcffe7`; notices are retained.

See the root BUILD.md for order/dependencies, docs/playback-sources.md for
measured playback results and limits, and THIRD_PARTY.md for licenses.
Both initial probing and actual decoded-pixel/Surface measurements are needed:
a visible `/dev/video*` or registered codec alone is not a decode pass.
