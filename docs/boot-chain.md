> 历史 bring-up 资料。当前构建与验收范围以 [BUILD.md](../BUILD.md) 和独立移植复盘为准。旧 alpha、TF、HEVC 与旧校验项不代表当前发布已验证状态；当前 HEVC 硬件节点停用，最终板上验收介质为 eMMC。

# Android 17 首启链核对

2026-11-04，固定 AOSP `android-17.0.0_r1`。官方 manifest 提交为
`5bc9a7ce1cd78dd53613bbfd0ebf506e1e4adb0f`，逐项目锁文件位于
`records/aosp-android17-locked-manifest.xml`。本次核对源码、板级配置和已经生成的
Ninja/Soong 配置，记录为 `records/first-stage-boot-chain-audit.json`。

首启顺序为 TF 卡 U-Boot → FAT 中的 zImage、gzip ramdisk、DTB → ramdisk
`/init` → system 切根 → `/system/bin/init selinux_setup` → 第二阶段 init。
extlinux 的 `androidboot.hardware=fireflyrk3288` 对应 ramdisk 根目录的
`/fstab.fireflyrk3288`，`androidboot.boot_devices=ff0c0000.mmc` 对应 TF 卡控制器。

当前 tag 的 first-stage init 支持上述 fstab 根目录位置。生成的 Ninja 已包含
ARM32 静态 `init_first_stage` 安装到 `ramdisk/init` 的规则、根目录 fstab 复制规则，
以及 `mkbootfs | gzip` 生成 `ramdisk.img` 的规则。system 镜像构建会把 root
目录与 system 内容合成根文件系统；first-stage 挂载 system 后切根，第二阶段
可执行文件位于新根的 `/system/bin/init`。

fstab 中 system、system_ext、product、vendor、metadata 的 GPT PARTLABEL
与打包器一致。metadata 提前挂载并随切根搬迁；userdata 在 `late-fs` 阶段按
未加密 ext4 挂载，随后触发 `nonencrypted`，启动 main/late_start 服务。
生成配置中的 GKI、动态分区、super 和 AVB 均关闭；该路径使用普通 ramdisk，
不依赖 vendor_boot/init_boot。

本次观察时 `ramdisk/init`、`ramdisk.img`、`system/bin/init` 和各分区镜像尚未生成。
完整构建后，打包器 `scripts/assemble-sd.py::check_boot_files()` 会读取实际 gzip
cpio，检查可执行 ARM32 `/init`、fstab 分区条目、zImage magic 和 DTB compatible。
最终整盘校验继续由 `./build.sh verify` 保存结果；板卡 TF 卡首启记录单独填写。
