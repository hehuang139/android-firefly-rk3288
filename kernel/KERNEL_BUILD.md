> Historical bring-up reference. For the final tested eMMC source profile and
> current validation limits use BUILD.md and docs/移植复盘.md. Old check counts
> and TF/HEVC instructions below are not current release validation.

# Firefly-RK3288 电视内核

当前电视产品使用 Linux **6.18.60-firefly-tvbox**，板级 compatible 为 `firefly,firefly-rk3288`。所有电视必需驱动编入内核：Hantro H.264、RK3288 独立 HEVC、HDMI 显示与 I2S 声音、GPIO 红外、USB HID、以太网、Panfrost 和 LZ4 zram。

## 源码与工具

内核归档为 `downloads/linux-6.18.60.tar.xz`，SHA-256 为 `3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e`，来自 kernel.org 的 2026-10-30 稳定版。`downloads/source-signature-verification.txt` 记录 Greg Kroah-Hartman 稳定版密钥的签名验证；指纹为 `647F28654894E3BD457199BE38DBBDC86092693E`。

配置为 `firefly-tvbox.config`，原板红外表为 `rc-firefly-rk3288.c`。`hevc/` 包含完整 GPL-2.0 HEVC 后端和针对 Linux 6.18 的驱动接入补丁；其来源、RK3288 寄存器差异与 Main8/NV12 范围见 [HEVC 说明](hevc/README.md)。H.264 继续使用 `ff9a0000` 的 Hantro，H.265 使用独立的 `ff9c0000` 单元、IRQ12 和 `ff9c0440` IOMMU。

构建器使用 Ubuntu GCC 11.4.0 的 `arm-linux-gnueabihf-` 工具链，默认 Docker 镜像为 `firefly-batocera-build:20261102`。可用本目录 Dockerfile 构建自己的镜像后，通过 `FIREFLY_BUILD_IMAGE` 选择。主机需要 Docker、Python 3、`rg` 和 `patch`。

## 构建

从本目录运行：

```sh
FIREFLY_KERNEL_JOBS=2 ./build-tvbox.sh
```

脚本使用 `multi_v7_defconfig`、电视配置片段及 `olddefconfig`，固定构建身份与时间，最多使用两核；源码和输出默认位于项目的 `tvbox-work/kernel/`。通过 `FIREFLY_TVBOX_KERNEL_WORK` 可以选择独立输出目录。构建只操作普通文件。

它编译共享 zImage 和两份 DTB，编译 Binder ABI 静态断言，运行配置/符号/设备树审计，然后复制：

- zImage → `device/firefly/rk3288/prebuilts/zImage`
- TF DTB → `device/firefly/rk3288/prebuilts/rk3288-firefly-android.dtb`
- eMMC DTB → `variants/emmc/boot/rk3288-firefly-android.dtb`
- 审计与完整配置 → `records/kernel-tvbox/`

再由项目的 `build.sh install` 同步 AOSP，重建 Android 后封装镜像。

## TF 与 eMMC

`rk3288-firefly-tvbox.dts` 是 TF 版本，启用 `ff0c0000.mmc`、禁用 `ff0f0000.mmc`；`rk3288-firefly-tvbox-emmc.dts` 继承同一硬件定义并反转两个状态。两者的其他节点和属性完全一致，使用同一个 zImage。选中的存储控制器限制为 50 MHz。

每版只暴露一个 Android 存储介质，防止两张具有相同 GPT PARTLABEL 的盘在 first-stage init 中发生命名竞争。extlinux 分别设置 `androidboot.boot_devices=ff0c0000.mmc` 或 `ff0f0000.mmc`；fstab 按分区名挂载。刷写方法见 [eMMC 安装说明](../docs/emmc-install.md)。

## Android 与遥控

ARMv7 用户空间使用 64 位 Binder IPC 布局：CPU 指针 4 字节，Binder 指针/size 字段 8 字节、协议版本 8。内核启用 binderfs、SELinux、seccomp、PSI、兼容内存/cpuset 控制器、DMA-BUF heap、同步 fence、eBPF、FUSE 和网络过滤。

GPIO 红外使用原板 GPIO7_A0，原厂 12 键表内建；Android 学习服务和专用键位布局见 [遥控说明](../device/firefly/rk3288/remote/README.md)。CEC 内核驱动与 rc-core 已编入；默认保留上游引脚定义，CEC 输入服务关闭，确认本板 HDMI pin13 走线后再按可选 DTS 配置启用。

`SYSCON_REBOOT_MODE` 将 `adb reboot bootloader` 写入 PMU 的 Rockchip 重启标记，由 U-Boot 进入 USB Fastboot。OTG 口为 USB peripheral，独立 USB-A host 仍可接遥控器和存储设备。

## 验证记录

电视内核审计（本地历史证据：`records/kernel-tvbox/audit.json`，未随源码发布） 检查实际交叉编译产物、请求配置、H.264/HEVC/音频/红外/CEC 链接符号、Binder ABI、两份设备树的单一启动介质与公共节点一致性，并记录产物 SHA-256。板上启动、声音、按键、待机和样片解码通过刷板验收记录结果。

原 Android 基础内核的历史记录保存在 `records/kernel/` 和 `records/kernel-reboot-mode/`。电视产品以 `records/kernel-tvbox/` 和 `records/kernel-latest.json` 为当前索引。

Linux 与 HEVC 后端保留 GPL-2.0 许可，DTS 使用上游 `(GPL-2.0+ OR MIT)`，构建与审计脚本为 MIT。
