# 原版 RK3399 构建与镜像检查

本流程面向 ARM64 Android 17，不能使用旧 `build.sh` 或 RK3288 的预编译文件。
当前记录了实际构建流程；完整系统镜像及新板启动仍以独立验收报告为准。

## 隔离源码和输出

我使用仓库 `manifests/` 中的固定 AOSP 基线，独立源码可写层和独立输出目录。
构建时 `device/firefly/rk3288` 必须不可见，否则同名模块会冲突。安装器会拒绝
这种情况。已有旧板环境应通过独立 checkout 或只读基线加独立 OverlayFS 隔离，
不删除旧设备目录来迁就新构建。

AOSP 输出应挂载在源码树下，以相对 `OUT_DIR=out` 使用。本轮平台测试模块
对绝对输出路径处理错误，曾使整个 Soong 图失败。独立输出不等于必须使用
绝对 `OUT_DIR`。通用 ARM64 bootstrap 与最终 RK3399 产品可以使用同一份新的
输出目录，不能复用旧 RK3288 目标二进制。

## 先生成真实 ARM64 工具链输入

在安装新设备树前，先用通用 ARM64 产品生成 NDK sysroot 和四个 CRT：

```sh
cd /path/to/isolated/aosp
export OUT_DIR=out
export SOONG_NINJA=ninja
export GOMAXPROCS=6
export SOONG_GOMEMLIMIT=24GiB
source build/envsetup.sh
lunch aosp_arm64-aosp_current-userdebug
m -j12 ndk_sysroot crtbegin_so crtbegin_dynamic crtend_so crtend_android
```

并发和内存值按构建机实际余量调整。本轮完整依赖图需要大量内存；启动构建
或看到百分比不等于 CRT 已生成。后续 FFmpeg 构建会核对真实 ARM64 对象。
不通过创建假内核、空共享库或借用 ARM32 `.so` 解除构建图依赖。

按照 [内核说明](../kernel/rk3399/README.md)、
[启动链说明](../bootloader/rk3399/README.md) 并行构建独立硬件产物，保留
`kernel-manifest.json` 和 `bootloader-manifest.json`。按
[Wi-Fi 说明](../device/firefly/rk3399/wifi/README.md) 准备 AP6356S 固件和许可证。
内核、DTB 和六个模块必须来自同一次通过校验的构建。

接着使用 `device/firefly/rk3399/media/build-ffmpeg.py`，显式给定 AOSP、
该 AOSP 的 `out`、独立工作目录和固定的干净 FFmpeg 源码。脚本产生新的
ARM64 库和头文件，记录来源和输出哈希。Mesa 的宿主工具必须对应同一固定
Mesa 源码，不能随意使用另一个版本的 `mesa_clc`。

## 安装产品源并构建

先把已验证的 `Image`、DTB、模块、固件与 FFmpeg 输出放进相应的 `prebuilts`
目录。公开源码默认没有第三方 APK 或节目源。个人构建另外使用已审查的私有
输入；官方 YouTube 与六款已有应用分别见它们的导入说明，不能把私有文件
复制进公开仓库再提交。

```sh
export FIREFLY_AOSP_ROOT=/path/to/isolated/aosp
export FIREFLY_ANDROID_OUTPUT=out
export FIREFLY_MESA_NATIVE_TOOLS=/path/to/matching/mesa-native/install/bin
export FIREFLY_ANDROID_JOBS=12
export FIREFLY_ENABLE_WIFI=true
bash build-rk3399.sh install
bash build-rk3399.sh lunch
bash build-rk3399.sh graph
bash build-rk3399.sh components
bash build-rk3399.sh build
```

Wi-Fi 开关只在全部匹配输入已准备后启用。使用构建工具实际返回的
`PRODUCT_OUT`，通常为 `out/target/product/rk3399`。组件构建通过后仍需完成
系统分区构建；不能用 APK 或某个 HAL 单独成功代替整机完成。

系统构建完成后，再检查实际安装目录和其中的 APEX。图形库检查两个 ABI，
服务使用 ARM64；音视频、遥控服务检查 ARM64。不能只用 NDK 链接桩证明
设备运行时会找到依赖。

```sh
python3 scripts/verify-graphics-elf.py --aosp /path/to/isolated/aosp \
  --product-out /path/to/isolated/aosp/out/target/product/rk3399 \
  --arch arm64_32 --report /private/reports/graphics.json
python3 scripts/verify-tv-media.py --aosp /path/to/isolated/aosp \
  --product-out /path/to/isolated/aosp/out/target/product/rk3399 \
  --arch arm64 --include-audio --include-remote \
  --extra-vendor-root /vendor/lib64/libswresample.so --report /private/reports/media.json
```

## 整盘文件与独立检查

把最终 Image、该产品的 gzip ramdisk、最终 DTB 和
`boot/rk3399/extlinux.conf` 放进一个干净的 `boot-files` 目录，结构为：

```text
boot-files/boot/Image
boot-files/boot/ramdisk.img
boot-files/boot/rk3399-firefly-android.dtb
boot-files/extlinux/extlinux.conf
```

`scripts/assemble-rk3399.py` 需要明确的 `--product`、`--boot-files`、
`--idbloader`、`--uboot`（U-Boot FIT）、`--loader-manifest`、`--kernel-manifest`、
`--simg2img` 和一个全新的 `--output` 普通文件。它不会打开块设备。
镜像为 12 GiB 静态 GPT；压缩下载大小不能替代写入后的容量需求。

随后用 `scripts/verify-rk3399.py`，对同一组输入和 `--image` 运行独立只读
检查，传入前面的 `--graphics-report` 和 `--media-report`，另给全新的 `--report`。
检查还将依赖报告中的库、链接器和 APEX 哈希逐项绑定到镜像实际文件。
检查包含双 GPT、启动文件、实际 ARM64 ELF、
加载窗口、内核/Loader 来源绑定、文件系统、分区内容和整盘 SHA-256。
离线报告的成功值是 `PASS_OFFLINE_NOT_BOOTED`，不是实机通过。

真正的 USB 下载 Loader 与磁盘上的 `idbloader.img` 是不同产物。
RK3399 的 USB Loader 按 `bootloader/rk3399/build-usb-loader.py` 单独生成。
不得使用旧 RK3288 RAM readlimit 补丁。接板后的验收见
[首次上板验收](rk3399-hardware-validation.md)。
