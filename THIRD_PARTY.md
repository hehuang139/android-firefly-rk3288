# Licenses and corresponding sources

The root MIT license applies only to original scripts carrying that identifier.
It does not relicense Android, Linux, U-Boot, Mesa, FFmpeg or third-party source.
Preserve per-file copyright/license notices. Android device/HAL/UI changes and
Codec2 code retain Apache-2.0 notices; full license text is under licenses/.

| Component | Exact source | License and local material |
|---|---|---|
| AOSP | android-17.0.0_r1; every project pinned in manifests/aosp-pinned.xml | Component licenses in upstream checkout |
| Linux | 6.18.60 tar SHA256 3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e | GPL-2.0 and file exceptions; complete cumulative patch/config/changed source in kernel/final; upstream COPYING included |
| U-Boot | v2024.01 tar SHA256 a03c3c2ba9d2bea5176c6406f1f3429a79e1147be242f5a07dbd9e89b3cc83c4 | GPL-2.0-or-later; bootloader/source and variants/emmc patches/config/build scripts |
| FFmpeg | Kwiboo/FFmpeg b57fbbe50c9b2656fad86a1a7eeabfd2b2a50935 | LGPL-2.1-or-later subject to configure options; device media patch/build script and licenses/ |
| Codec2 bridge | LineageOS/android_external_ffmpeg_codec2 00f6f65c7ef381470efbcfca8c0316bdcdfcffe7 | Apache-2.0; complete adapted device media/codec2 sources |
| minigbm | AOSP ce79bbee67b3e2ea7abb110e1415e9ceceaa6471 | BSD-3-Clause; patches/minigbm and licenses/ |
| Mesa | AOSP 875160ed32cc5bc32777fa04870a0a57ed38c987 | Component licenses, predominantly MIT; graphics integration |
| aospext | 8c3075ffb6005b1c317e69d4da4071dc2403e0f9 | Apache-2.0; graphics/aospext |

Upstream sources are fetched by the documented build; their full archives are
not duplicated here. Before distributing GPL binaries, supply the exact full
corresponding source, local patches, configuration and build material, rather
than relying only on a repository URL. FFmpeg shared-library distribution also
requires preserving LGPL notices and the recipient's relinking/replacement
rights. No application APK, account token, stream catalog or proprietary
Rockchip/Mali Android binary is redistributed by this source repository.

The RAM Loader patching/checking utility under tools/ram-loader is Apache-2.0.
Its license does not grant redistribution rights for any vendor loader binary;
no vendor loader binary or Windows driver is included.

Source URLs:
- https://android.googlesource.com/platform/manifest/+/android-17.0.0_r1/
- https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.18.60.tar.xz
- https://github.com/u-boot/u-boot/tree/v2024.01
- https://github.com/Kwiboo/FFmpeg/tree/b57fbbe50c9b2656fad86a1a7eeabfd2b2a50935
- https://github.com/LineageOS/android_external_ffmpeg_codec2/tree/00f6f65c7ef381470efbcfca8c0316bdcdfcffe7
