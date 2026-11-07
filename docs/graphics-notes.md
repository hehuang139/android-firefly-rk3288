> 历史 bring-up 资料。当前构建与验收范围以 [BUILD.md](../BUILD.md) 和独立移植复盘为准。旧 alpha、TF、HEVC 与旧校验项不代表当前发布已验证状态；当前 HEVC 硬件节点停用，最终板上验收介质为 eMMC。

# Android 17 / Firefly-RK3288 图形栈

目标为原版 Firefly-RK3288 的 Mali-T760 + Rockchip VOP + HDMI。采用主线内核的
Panfrost DRM 驱动、Mesa Panfrost OpenGL ES、AOSP minigbm、AOSP DRM hwcomposer。
首轮由 GPU 完成合成，DRM 负责 HDMI 扫描输出。

## 固定来源

- Android：`android-17.0.0_r1`。
- Mesa：AOSP `platform/external/mesa3d`，提交
  `875160ed32cc5bc32777fa04870a0a57ed38c987`，`VERSION` 为 `26.1.0-devel`。
- minigbm、drm_hwcomposer：同一 Android 标签内的对应项目，最终使用
  `repo manifest -r` 记录整个工程的提交。
- Android/Meson 桥接：GloDroid `aospext`，提交
  `8c3075ffb6005b1c317e69d4da4071dc2403e0f9`。代码在 `graphics/aospext/`，
  保留 Apache-2.0 许可、原作者版权及 `UPSTREAM` 记录。
- 宿主环境：Debian 13 trixie-slim，OCI 索引摘要
  `sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4`。
  Dockerfile 中安装 LLVM/Clang 19、libclc 19、SPIRV-LLVM-Translator 19、
  SPIRV-Tools、Meson、Ninja；实际包版本由脚本输出 `host-packages.tsv`。

## 为什么增加 Meson 桥接

AOSP 17 的 Mesa 源码包含 Panfrost，但现有 Soong 文件没有提供该板所需的
Panfrost EGL/GLES 模块。桥接从 Android 构建系统提取 ARM32 编译器、头文件、
Bionic 和 vendor 库链接参数，再使用 Meson 编译同份 Mesa。它生成：

- `/vendor/lib/egl/libEGL_mesa.so`
- `/vendor/lib/egl/libGLESv1_CM_mesa.so`
- `/vendor/lib/egl/libGLESv2_mesa.so`
- `/vendor/lib/libgallium_dri.so`

RK3288 的 Mali-T760 属于 Midgard v5。Mesa 文档列出其 OpenGL ES 3.1 支持；
PanVK 的支持列表不包含 T760，因此本设备不声明 Vulkan 功能。

## 先构建同源宿主工具

Mesa 26.1 的 Panfrost 构建会编译内置着色器，需要先构建 **同一源码版本** 的
`mesa_clc`、`vtn_bindgen2` 和 `panfrost_compile`。
直接关闭 LLVM 又不提供这些工具，会在配置/生成阶段失败。

```bash
./graphics/host-tools/build.sh \
    /absolute/path/to/aosp \
    /absolute/path/to/mesa-native
```

脚本检查 Mesa 提交，构建 Docker 镜像
`firefly-android17-builder:20261104`，然后原生编译三个工具并安装到
`mesa-native/install/bin`。脚本还用 Mesa 自带的三份 libpan shader，执行
`mesa_clc → vtn_bindgen2 → panfrost_compile`，覆盖 Panfrost 架构
4、5、6、7、9、10、12、13；其中 5 为 T760 的 Midgard 代际。
工具动态依赖 LLVM 19，Android 构建应在同一个
Docker 镜像中执行，挂载 AOSP 与 `mesa-native` 为相同绝对路径，并把该
`install/bin` 加入 `PATH`。镜像创建了 uid 1000 的 `builder` 账户；运行时可用
`--user "$(id -u):$(id -g)"`。

```bash
docker run --rm -it --user "$(id -u):$(id -g)" \
    -v /absolute/path/to/aosp:/absolute/path/to/aosp \
    -v /absolute/path/to/mesa-native:/absolute/path/to/mesa-native \
    -w /absolute/path/to/aosp \
    firefly-android17-builder:20261104 bash
# 在容器内：
export PATH=/absolute/path/to/mesa-native/install/bin:$PATH
source build/envsetup.sh
# 再按设备构建说明选择 lunch 和构建目标。
```

宿主工具默认 8 个并发任务，`MESA_NATIVE_JOBS` 可调。
Android 内部的 Mesa 构建默认 8 个并发任务，`FIREFLY_MESA_JOBS` 可调。

## 设备接入

安装整个 `graphics/` 为 `device/firefly/rk3288/graphics/`。
`BoardConfig.mk` 包含 `graphics/BoardConfigGraphics.mk`，产品 `device.mk` 继承
`graphics/graphics.mk`。allocator、mapper、composer 模块自带 VINTF 片段；
设备独立 manifest 不应重复添加这三组 HAL。

内核必须提供 `CONFIG_DRM_ROCKCHIP`、`CONFIG_DRM_PANFROST`、Rockchip HDMI、
DMA-BUF 与共享缓冲区同步。实际板卡启动后确认 `/dev/dri/card*`、
`/dev/dri/renderD*`、HDMI connector、gralloc 与 composer 服务状态，再检查
SurfaceFlinger 的实际 EGL renderer 和 OpenGL ES 版本。

## 当前验证记录

2026-11-04：已读取 Android 17 标签内的 ARM32 构建入口、minigbm 的 Rockchip
后端、DRM composer3 模块和 Mesa Panfrost Meson 构建文件；已固定上述来源，
并完成脚本 Bash 语法检查。Debian 13 合一构建容器已实际构建成功；
Mesa 宿主工具的 647 项 Ninja 任务全部完成，三个必需工具已安装；
上述八种架构的 libpan shader 生成链全部通过。实际包版本、工具 SHA-256 和
验证结果保存在 `graphics/validation/`。
设备图形库、Android 全量构建及 HDMI 桌面需在构建和板卡运行后逐项记录结果。

参考：

- https://android.googlesource.com/platform/manifest/+/refs/tags/android-17.0.0_r1
- https://android.googlesource.com/platform/build/+/android-17.0.0_r1/target/product/aosp_arm.mk
- https://android.googlesource.com/platform/external/mesa3d/+/android-17.0.0_r1/
- https://android.googlesource.com/platform/external/minigbm/+/android-17.0.0_r1/
- https://android.googlesource.com/platform/external/drm_hwcomposer/+/android-17.0.0_r1/
- https://github.com/GloDroid/aospext/tree/8c3075ffb6005b1c317e69d4da4071dc2403e0f9
- https://docs.mesa3d.org/drivers/panfrost.html

## Android 17 渲染后端核对

当前 tag 的 SurfaceFlinger 在未指定 RenderEngine backend 时，仅在 Vulkan
初始化成功后才选择 Vulkan；初始化失败会保持 OpenGL/Ganesh/threaded。
系统仍有 `libvulkan` loader，但本板没有 Vulkan 硬件 HAL，loader 的 stub
不能提供所需 physical device，因此此选择会回到 GL。`debug.hwui.renderer=skiagl`
在本 tag 仍有效，它独立控制 HWUI。依据为
`SurfaceFlinger.cpp` 的 backend 选择、`SkiaVkRenderEngine::canSupport`、
`VulkanInterface` 的物理设备检查及 HWUI `Properties.cpp`。
