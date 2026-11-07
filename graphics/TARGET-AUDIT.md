# Android 17 目标图形栈源码核对

2026-11-04；核对 `android-17.0.0_r1`，Mesa 提交
`875160ed32cc5bc32777fa04870a0a57ed38c987`。

## 库名与安装路径

`src/mesa/glapi/shared-glapi/meson.build` 把 glapi 定义为不安装的静态库。
`src/gallium/targets/dri/meson.build` 将其链接进 Gallium，在 Android 平台
明确使用 `gallium_dri` 名称，因此目标为 `/vendor/lib/libgallium_dri.so`。
包装层不应再要求已不独立安装的 `libglapi.so`。

同一文件的 Gallium `install: true` 使用 `--libdir lib`，并非旧版的 `lib/dri`。
EGL/GLES 经包装模块安装为 `/vendor/lib/egl/lib{EGL,GLESv1_CM,GLESv2}_mesa.so`。
现有 AOSP Mesa `Android.bp` 没有定义上述四个模块名；包装模块不会与其重名。

## mapper 4/5 和稳定 C 接口

包装层在 SDK >= 35 时添加 `libui` 依赖和 `ui.pc`，不再走旧版 mapper@4.0
专用 Meson 入口。Mesa 的 `src/util/u_gralloc/meson.build` 在找到 `ui` 时选择
`u_gralloc_imapper5_api.cpp`，通过 `GraphicBufferMapper` 访问缓冲区元数据。
宏 `USE_IMAPPER4_METADATA_API` 仍保留旧名称，不能仅凭宏名称判断为旧 mapper。

Android 17 `GraphicBufferMapper` 的 `ui::PlaneLayout` 是 AIDL `PlaneLayout`
类型别名；`getPixelFormatFourCC`、`getPixelFormatModifier`、`getPlaneLayouts`
以及需要的 metadata 访问函数仍存在。minigbm 的 `mapper.minigbm` 提供稳定 C
IMapper v5，allocator 为 AIDL 服务。`libui` 自身负责适配 mapper 版本。

Mesa 的 CrOS gralloc fast path 先尝试旧 `gralloc.*` 模块；本产品只安装稳定
mapper，随后走已编译的 `GraphicBufferMapper` 路径。

## 独立的 Rockchip 显示和 Panfrost 渲染设备

minigbm 的 `cros_gralloc_driver.cc` 先尝试 render 节点，按 DRM driver name
匹配后端；Panfrost 没有 minigbm 后端，因此会继续尝试 card 节点，最终匹配
名为 `rockchip` 的后端。当前 `platform=generic` 没有定义 `DRV_ROCKCHIP`，
真正使用的是 `dumb_driver.c` 中 `#ifndef DRV_ROCKCHIP` 下的
`INIT_DUMB_DRIVER(rockchip)`，支持线性 scanout/render 缓冲区。

具体入口为 `cros_gralloc_driver` 构造器 → `init_try_nodes` →
`init_try_node` → `drv_create(fd, NULL)`。`init_try_nodes` 先遍历
`renderD128` 至 `renderD190`，再遍历 `card0` 至 `card62`；只有成功创建
minigbm driver 才返回，并不会在第一个能打开的节点处停止。
`drv_get_backend` 用 `drmGetVersion(fd)->name` 与后端名称精确匹配，缺少
匹配时返回 NULL；`init_try_node` 随后关闭该 fd 并继续枚举。因此 Panfrost
render 节点不会被误选，也不会阻止扫描 Rockchip primary 节点。

内核 6.18.60 的 `rockchip_drm_driver` 提供
`DRIVER_MODESET | DRIVER_GEM | DRIVER_ATOMIC`，名称为 `rockchip`，不带
`DRIVER_RENDER`；`panfrost_drm_driver` 提供
`DRIVER_RENDER | DRIVER_GEM | DRIVER_SYNCOBJ`，名称为 `panfrost`。
minigbm 的 `drv_backend_list` 无条件包含 `backend_rockchip`，其名称恰为
`rockchip`。`Android.bp` 的 core files 同时包含 `rockchip.c` 和
`dumb_driver.c`，但前者由 `#ifdef DRV_ROCKCHIP` 包围；所选
`platform=generic` 的额外编译宏只有 `HAS_DMABUF_SYSTEM_HEAP`，故前者不参与
后端实现，后者生成对应的 `backend_rockchip`。本内核关闭 SIMPLEDRM、VKMS、
UDL 和 VIRTIO_GPU，避免额外虚拟显示后端参与匹配。

设备 `ueventd` 沿用 AOSP 的 `/dev/dri/* 0666 root graphics`。普通应用不会
默认取得 `graphics` 补充组，Mesa EGL 需要直接打开 Panfrost render 节点，
同进程 mapper V5 的 `cros_gralloc_driver` 还必须打开 Rockchip primary 节点，
以执行 `DRM_IOCTL_PRIME_FD_TO_HANDLE`。仅确保 allocator 服务可打开节点不足以
覆盖应用内导入路径，因此不能将 card 或 render 节点改为 `0660 system graphics`。
默认枚举已经覆盖所需 primary 节点，不需要额外选择设备的属性。
固定源码的检查结果保存在 `validation/minigbm-device-selection.json`；应用 GID、
ueventd import/匹配顺序和 DMA heap 权限核对见
`records/graphics-device-access-audit.json`（项目根目录）。

`/dev/dma_heap/system` 恢复上游的 `0444 system system`，因为 libdmabufheap
以 `O_RDONLY` 打开后通过 ioctl 分配。minigbm allocator 使用 system heap
分配共享元数据，mapper 使用收到的 FD；`linux,cma` 与 `reserved` 当前不参与
该路径，保持 `0660 system graphics`。

Mesa 的 `droid_open_device` 对硬件路径明确选择 `DRM_NODE_RENDER`，随后用
Panfrost 渲染节点创建 screen；Android EGL 直接链接 Gallium，并使用其
静态 pipe-loader driver descriptor。Rockchip 分配的 DMA-BUF 由 EGL 导入，
最终交给 DRM composer 在 Rockchip VOP/HDMI 上扫描输出。

`with_gallium_panfrost` 自动启用 kmsro 支持。旧桌面 DRI loader 使用的
`rockchip_dri.so`/`panfrost_dri.so` 别名由单独的 dril 构建产生，Android EGL
当前这条直接调用路径不需要安装这些别名。

## 首启合成方式与线性缓冲区

同标签 drm_hwcomposer 提交为
`87daba89b05fabc7f1e9316e3f283f19fd0c45cd`，minigbm 提交为
`ce79bbee67b3e2ea7abb110e1415e9ceceaa6471`。

当前 drm_hwcomposer 的 `utils/properties.cpp` 不读取旧的
`ro.vendor.hwcomposer.mode`。实际开关为 `vendor.hwc.backend_override`，
`backend/BackendManager.cpp` 用它选择 backend；`backend/ClientBackend.cpp`
的 planner 直接调用 `GetFlattenedComposition`，将所有层（含 cursor）交给
SurfaceFlinger 的 GPU client target。产品使用
`vendor.hwc.backend_override=client`。

`ro.vendor.hwc.use_overlay_planes=0` 使
`drm/DrmDisplayPipeline.cpp::GetUsablePlanes` 不加入 overlay plane，保留
primary plane 扫描输出。单独关闭 overlay 并不能强制全部 client composition，
因为 generic planner 仍可直接扫描某个 layer，且 cursor plane 有独立分支；
因此首启同时选择上面的 client backend。两项 vendor 属性需在设备策略中
声明属性类型，并允许 composer 读取。

minigbm `cros_gralloc_driver::allocate` 调用 `drv_bo_create`；当前 generic
Rockchip 后端没有 `bo_compute_metadata`，所以沿 `drv_dumb_bo_create` →
`drv_dumb_bo_create_ex` 路径，调用标准 `DRM_IOCTL_MODE_CREATE_DUMB`，用内核
返回的 pitch 和 allocation size 记录缓冲区布局。generic 后端仅注册
`LINEAR_METADATA`，modifiers 入口也只接受 `DRM_FORMAT_MOD_LINEAR`；映射
使用标准 `DRM_IOCTL_MODE_MAP_DUMB`。它不生成 AFBC，首启无需增加禁压缩属性。

`drv_helpers.c` 为 generic 分配按 64 像素 tile 对齐尺寸；YV12 单独处理
chroma 平面。Linux `rockchip_gem_dumb_create` 再把 pitch 按 64 字节对齐。
这与启用 `DRV_ROCKCHIP` 后才使用的 ChromeOS 专用 `rockchip.c` 路径不同；
后者依赖 `DRM_IOCTL_ROCKCHIP_GEM_CREATE` / `GEM_MAP_OFFSET` 私有接口，主线
6.18.60 Rockchip 没有注册这些私有 ioctl。本产品保持 generic 配置并使用
主线已有的 dumb-buffer 接口。

Panfrost 的 `pan_resource.c::panfrost_resource_from_handle` 接收 DMA-BUF fd，
读取导出的 stride/offset/modifier，并支持 `DRM_FORMAT_MOD_LINEAR`；缺失
modifier 时也按 linear 处理。`panfrost_kmod_bo_import` 获取导入对象的 GPU
地址，内核 6.18.60 的 `panfrost_gem_prime_import_sg_table` 把 Rockchip 导出的
scatter/gather buffer 接入 Panfrost 映射。此核对确认所选路径和格式相容；
实际分配、GPU 导入及 HDMI 扫描输出需在板卡上记录。

## EGL 驱动选择

Android 17 `frameworks/native/opengl/libs/EGL/Loader.cpp` 保留
`RO_DRIVER_SUFFIX_PROPERTY = "ro.hardware.egl"`，默认 native driver 搜索及
显式选择 native 的路径都会读取它。`load_system_driver` 将 `mesa` 后缀拼为
`libEGL_mesa.so`、`libGLESv1_CM_mesa.so`、`libGLESv2_mesa.so`，在 ARM32 的
`/vendor/lib/egl` 下查找。`ro.hardware.egl=mesa` 因此继续有效。
此处没有指定 `persist.graphics.egl`、`ro.egl.apex` 或可更新驱动 APK；产品
设置 `ro.gfx.angle.supported=false`，首启保持 Mesa native GLES 路径。

## PATH 与并发变量

AOSP `build/soong/ui/build/path.go` 将去重后的原始 PATH 保存到
`$OUT_DIR/.path_interposer_origpath`。包装层只在 Meson 子构建中恢复此 PATH。
在执行 `source build/envsetup.sh` 前加入 PATH 的同源 native 工具目录会保留。
子构建开始前检查 `mesa_clc`、`vtn_bindgen2`、`panfrost_compile` 可找到。

AOSP `ui/build/ninja.go` 在运行 Ninja 前过滤环境变量，默认不会保留
`FIREFLY_MESA_JOBS`。因此包装层改为在 Kati 解析时捕获它，再显式传给子
Make；未指定时为 8。无需打开 `ALLOW_NINJA_ENV`。

## Make / Soong 边界

AOSP 17 的 Android.mk denylist 包含 `external/`，未包含本设备使用的
`device/firefly/`；包装代码因此放在设备目录。产品显式将包装 Android.mk
加入 `PRODUCT_ALLOWED_ANDROIDMK_FILES`，也兼容仅解析产品允许列表的模式。
包装层不使用已废弃的 `BUILD_BROKEN_ANDROIDMK_EXPORTS`。

RK3288 只有一个 ARM32 架构，使用 `LOCAL_MULTILIB := first`，不会实例化
2ND_ARCH 分支。库模块名与提取编译参数的 sharedlib/executable dummy 模块
分别独立。现有包装层未设置 `LOCAL_MODULE_TARGET_ARCH`，预编译产物通过
`BUILD_PREBUILT` 注册，未使用 `PRODUCT_COPY_FILES` 复制 ELF。

## 验证状态

native 编译及实际 shader 生成链结果见 `validation/native-build.json`。
本页其余结论来自固定版本源码与构建配置核对；Android 目标库的实际编译、
ELF 架构、动态依赖及设备运行结果仍需随完整构建记录。
