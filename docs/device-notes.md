> 历史 bring-up 资料。当前构建与验收范围以 [BUILD.md](../BUILD.md) 和独立移植复盘为准。旧 alpha、TF、HEVC 与旧校验项不代表当前发布已验证状态；当前 HEVC 硬件节点停用，最终板上验收介质为 eMMC。

# 原版 Firefly-RK3288 Android 17 设备配置

配置入口为 `device/firefly/rk3288/aosp_firefly_rk3288.mk`，目标
`aosp_firefly_rk3288-aosp_current-userdebug`。CPU 使用 ARMv7-A NEON，
按 Cortex-A15 指令调度（物理 CPU 为 Cortex-A17）；只构建 32 位应用和系统服务。
Android 17 的 Binder 用户空间默认使用 64 位协议，Linux 6.18 Binder 驱动使用
该协议，已不提供旧的 `CONFIG_ANDROID_BINDER_IPC_32BIT` 选项。这里没有设置已经废弃的
`TARGET_USES_64_BIT_BINDER`，也没有使用已移除的 `BOARD_BUILD_SYSTEM_ROOT_IMAGE`。

## 启动与存储接口

原版 `firefly,firefly-rk3288`，不适用于 Reload/Plus。内核预编译位置是
`device/firefly/rk3288/prebuilts/zImage` 和
`device/firefly/rk3288/prebuilts/rk3288-firefly-android.dtb`。
最新内核来源和构建记录由 `records/kernel-latest.json` 索引到
`records/kernel-reboot-mode/`；`kernel-port/` 是普通重建工作目录。

首启路径为 SD 上的 U-Boot → FAT `extlinux.conf` → ARM zImage + gzip cpio
`ramdisk.img` + DTB → Android first-stage init → 静态 GPT system/vendor 等分区。
`boot.img` 使用 header v2 额外生成，供拆包验证和后续启动适配；首个 SD 方案不要求
U-Boot 解析 Android boot.img，也不使用 vendor_boot/init_boot、GKI、A/B 或 super。

`androidboot.hardware=fireflyrk3288` 必须在 extlinux 的 APPEND 中保留，
否则 init 不会选中本设备的 fstab 和 rc。`BoardConfig.mk` 的启动参数必须由镜像打包脚本
同步到 extlinux，因为直接 bootz 不会读取 boot.img 中的参数。
`androidboot.boot_devices=ff0c0000.mmc` 用于识别 SD 的 by-name 分区链接。
TF DTB 禁用板载 eMMC 节点。

eMMC 变体使用独立 DTB 和 U-Boot，boot device 为 `ff0f0000.mmc`，并关闭 TF
控制器。两种介质共用 Android 分区、ramdisk、fstab 和 zImage，通过各自的
bootdevice 参数及 GPT PARTNAME 找到分区；具体入口见 [双介质打包接口](boot-media.md)。

分区协议如下；容量是构建镜像的上限。

| GPT PARTLABEL | 大小 | 挂载 |
| --- | ---: | --- |
| boot | 256 MiB，16 MiB 起，FAT32，卷标 FIREFLYBOOT | U-Boot 读取 |
| system | 4096 MiB | first stage `/system`，随后切换根 |
| system_ext | 1024 MiB | first stage，只读 |
| product | 1024 MiB | first stage，只读 |
| vendor | 512 MiB | first stage，只读 |
| metadata | 32 MiB | first stage，ext4 |
| userdata | 5327 MiB；AOSP 初始镜像 5120 MiB | late mount `/data` |

打包脚本为 metadata 创建 ext4，并将 userdata 扩展至其分区大小。
分区名字必须和 `init/fstab.fireflyrk3288` 完全一致。userdata 没有 FBE、
metadata encryption 或 dm-default-key 选项，适配当前主线内核的开发首启。
这版是未加密的 userdebug 系统，AVB 关闭，内核参数选择 SELinux permissive。

## 显示、输入与网络

图形通过独立 `graphics/BoardConfigGraphics.mk` 和 `graphics/graphics.mk` 接入，
使用 Mesa/Panfrost EGL/GLES、AOSP minigbm allocator/mapper、DRM HWC3。
AOSP 模块自带 VINTF 片段，设备 manifest 不重复声明它们。
Mali-T760 没有启用 Vulkan。显示器通过主线 Rockchip DRM/HDMI 驱动读取 EDID。
鼠标/键盘走 Linux evdev，权限由 ueventd 配置，界面启用导航栏并关闭电话/SMS 能力。
初始连接使用 Ethernet；没有为尚未移植的 Wi-Fi、蓝牙或摄像头声明硬件 feature。

普通应用的 GID 与应用 UID 相同，补充组来自 permission/global GID 和应用存储组，
不会默认取得 `graphics` 组。Mesa EGL 在应用进程内以 `O_RDWR` 打开 Panfrost
`renderD*`；同进程 minigbm mapper V5 还会打开 Rockchip `card*`，用于导入
DMA-BUF。因此设备 ueventd 沿用 AOSP 的 `/dev/dri/* 0666 root graphics`。
仅把 render node 放开仍会导致 mapper 的 primary node 初始化失败。ueventd
在父配置读完后处理 import，设备权限按规则逆序匹配，vendor 规则会覆盖 system 默认。

`/dev/dma_heap/system` 同样沿用 AOSP 的 `0444 system system`：libdmabufheap
先以 `O_RDONLY` 打开 heap，再通过 allocation ioctl 分配；heap 设备本身不需要写权限。
当前 minigbm allocator 用它分配共享元数据，同进程 mapper 映射收到的 DMA-BUF FD。
`linux,cma` 和 `reserved` 不参与这条图形分配路径，保留 `0660 system graphics`。
源码与权限配置核对见 `records/graphics-device-access-audit.json`；构建产物中的
`vendor/etc/ueventd.rc` 必须包含上述 DRM 与 system heap 规则。

USB ADB 使用原版 RK3288 的 `ff580000.usb` OTG 控制器与 Android 公共 configfs rc。
板级 `on init` 创建 gadget、ADB FunctionFS function、configuration 及字符串，
挂载 `/dev/usb-ffs/adb` 后选择 configfs；公共 rc 在 adbd 写入 descriptors、
设置 `sys.usb.ffs.ready=1` 后才绑定 UDC。移植补丁删除 adbd 在 USB endpoint
不存在时自动启用 TCP/VSOCK 5555 的分支，保留主机密钥认证。
默认没有配置网络 ADB。USB host 接口用于键盘、鼠标；
OTG 接电脑用于日志和调试。UDC 名称和实际 USB 角色需要在板上核对。
解析顺序、失败行为和复现验证见 `docs/usb-adb.md`。

ZRAM 使用 LZ4、50% RAM。开发首启通过 wakelock 并关闭框架自动 suspend 保持 HDMI，
板上电源管理适配后再替换该策略。

## 基础 HAL 和待实测功能

health/power/memtrack/lights 使用 AOSP reference 服务。无电池开发板以供电运行。
KeyMint 和 Gatekeeper 是 AOSP 的 nonsecure 软件实现，密钥与锁屏鉴权没有 TEE 隔离。
音频使用 AOSP `com.android.hardware.audio` reference APEX，以提供框架音频服务；
**HDMI 声卡路由尚未实现**，不能以有内核声卡节点来声称 Android HDMI 已可出声。
没有添加商业 GPU blobs、GApps、Widevine、硬件视频编解码或经过验证的 Wi-Fi HAL。

SELinux policy 为 HWC3、allocator 和软件 KeyMint 添加了明确的可执行标签，
为 mapper/minigbm/gallium 设置同进程 HAL 库标签。EGL 目录沿用 AOSP 自带的
`same_process_hal_file`。添加的是窄范围 DRM/DMA-BUF 访问，未跳过 neverallow 检查。
首启内核 permissive 模式用于采集实际拒绝记录；不能据此标记 SELinux enforcing 已完成。

## 本次核对记录

已从 `android-17.0.0_r1` 核对：

- `build/make/target/board/generic/BoardConfig.mk`、`target/product/aosp_arm.mk`：
  ARMv7 NEON 与 Binder64 的真实目标仍存在。
- `build/make/core/{config.mk,board_config.mk,Makefile}`：
  boot header v2、普通 gzip ramdisk、预编译 kernel/DTB 和独立 ext4 分区变量。
- `system/core/init/{first_stage_init.cpp,first_stage_mount.cpp}`：
  system first-stage mount 和切换根流程。
- `external/drm_hwcomposer/Android.bp`：HWC3 模块名与 composer3 AIDL V5。
- `external/minigbm/Android.bp` 和 `cros_gralloc/{aidl,mapper_stablec}/Android.bp`：
  allocator AIDL V3、mapper native V5，以及泛用 Rockchip backend。
- `hardware/interfaces` 中 health/power/memtrack/lights、Gatekeeper nonsecure、
  KeyMint nonsecure、audio reference APEX 的实际模块定义。
- `frameworks/base/core/res/res/values/config.xml`：使用的框架 overlay 名均存在。
- 设备配置 4 个 XML 已用 Python XML parser 解析；Makefile 续行格式已检查。

完整 AOSP `droid` 和后续增量构建已成功，包含 VINTF/SELinux 及基础 HAL 构建。
实际产物的 ADB 49 项检查（本地历史证据：`records/usb-build-artifact-validation.json`，未随源码发布）、
8 个图形入口的依赖检查（本地历史证据：`records/graphics-elf-product-validation.json`，未随源码发布） 及
Android 文件系统分区 325 项检查（本地历史证据：`records/android-partitions-focused.json`，未随源码发布） 已通过。
TF 和 eMMC 完整整盘分别通过 520/520、522/522 项检查，含 GPT、加载器、
启动文件、文件系统、ADB 和图形文件对照；板上首启和外设运行结果待记录。

## 启动契约独立核查补充

- 本 tag 的 `build/release/release_config_map.textproto` 将 `aosp_current`
  映射至 `cp2a`；`cp2a` 继承 `mainline_2026_04` 和 `cp1a`。
  本设备 lunch 使用这一正式 tag 内的 release 配置，未选用独立的 `trunk_staging` flag 集。
- `init_first_stage_defaults` 的真实模块属性为 `stem: "init"`、
  `ramdisk: true`、`install_in_root: true`，所以 ramdisk 中应生成可执行 `/init`。
- Android 17 的 `system/fs/fs_mgr/libfstab/fstab.cpp` 明确在早期查找
  `/fstab.<hardware>`，后期优先查找 `/vendor/etc/fstab.<hardware>`；本配置同时安装这两份。
- 实际执行了本 tag `build_image.py` 中 `SetUpInDirAndFsConfig` 原函数，输入小型
  root/system 目录样本：函数把 `TARGET_OUT/bin/init` 放进镜像 `/system/bin/init`，
  并把镜像挂载点设置为 `/`。first-stage 将该镜像挂到旧根 `/system` 后 `SwitchRoot`
  所得新根中仍能以 `/system/bin/init` 启动第二阶段。记录见
  重建工作根的 `logs/device-system-root-layout.json`；该历史检查使用小型目录样本。
  后续实际 system.img 中的 init 路径和解释器已在 Android 分区检查中核对。
- GPT 打包函数独立生成了 12 GiB 稀疏测试磁盘，`sgdisk -v` 返回无问题，
  `sfdisk -J` 读取的分区名称/容量与 fstab 一致，userdata 为 5327 MiB。
  历史记录位于重建工作根的 `logs/device-boot-contract-gpt.json`，当时只验证分区表。
- `androidboot.boot_devices=ff0c0000.mmc` 由 fs_mgr 直接读取，init 的 DeviceHandler
  将对应平台设备生成 `/dev/block/by-name/<PARTNAME>`。因此挂载依赖 GPT PARTNAME，
  不依赖 ext4 label；AOSP system-as-root 镜像的文件系统 label 为 `/` 也是正常结果。
- 已有 U-Boot 配置开启 EFI/GPT 分区识别；其 bootstd 在无 bootable 分区时扫描首分区，
  与当前 boot=FAT32、GPT basic-data type、attributes=0 的布局一致。

## 目标构建接入修正

Android 17 的 `TARGET_PREBUILT_KERNEL` 只指定输入路径，核心 Makefile 不会自动
为 `$(PRODUCT_OUT)/kernel` 添加复制规则。本配置通过 `PRODUCT_COPY_FILES` 显式
安装 `prebuilts/zImage:kernel`，与同 tag 的 HiKey 接入方式一致。DTB 由
`BOARD_PREBUILT_DTBIMAGE_DIR` 对应的核心规则生成 `dtb.img`。

`BOARD_USES_GENERIC_KERNEL_IMAGE` 保持空值：本 tag 向 Soong filesystem config
转换此变量时以非空为 true；字面 `false` 会被当成 true。本设备使用普通
非 GKI 启动方式，Make 和 Soong 两侧都应为关闭状态。
