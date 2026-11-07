> Historical bring-up reference. For the final tested eMMC source profile and
> current validation limits use BUILD.md and docs/移植复盘.md. Old check counts
> and TF/HEVC instructions below are not current release validation.

# TF / eMMC 镜像打包接口

`scripts/assemble-sd.py` 和 `scripts/verify-sd.py` 均支持
`--boot-medium sd|emmc`，默认是 `sd`。两种镜像共用 12 GiB 的 GPT 几何、
Android 分区镜像、内核和 ramdisk；使用各自的 DTB、extlinux 配置和加载器。

| 项目 | TF：`sd` | eMMC：`emmc` |
|---|---|---|
| Android boot device | `ff0c0000.mmc` | `ff0f0000.mmc` |
| Linux SD 控制器 | `okay` | `disabled` |
| Linux eMMC 控制器 | `disabled` | `okay`，50 MHz |
| U-Boot 启动目标 | bootflow `mmc1` | 明确 `sysboot mmc 0:1` |
| 启动输入目录 | `bootloader/` 和板级 `prebuilts/` | `variants/emmc/bootloader/`、`variants/emmc/boot/` |

eMMC 用户区至少需 12 GiB，通常需要标称 16 GB 或更大的设备。
电视版默认文件为 `tvbox-artifacts/firefly-rk3288-tv-android17-sd-alpha.img` 与
`tvbox-artifacts/firefly-rk3288-tv-android17-emmc-alpha.img`；压缩后追加 `.xz`。
本轮 TF 独立检查 518/518 项通过；eMMC 和后续压缩打包以
`tvbox-artifacts/build-status.json`、`image-validation.json`、
`emmc-image-validation.json` 及 `SHA256SUMS` 为准。

常规打包在 `tvbox-port/` 执行 `./build.sh image` / `./build.sh verify`（TF），
或 `./build.sh image-emmc` / `./build.sh verify-emmc`（eMMC）。下文是相同介质
约定的底层接口；安装分别见 [TF 首启指南](tf-install.md) 和
[eMMC 安装指南](emmc-install.md)。

## eMMC 输入目录

从源码包开始时，先完成 [重建指南](rebuild.md) 第 2 节的共享内核、TF DTB
安装和第 3 节的 TF U-Boot 构建。`variants/emmc/rebuild.sh` 开头要记录这些
共享输入的哈希，随后才构建 eMMC 的独立 DTB 和 U-Boot。按
[eMMC 变体说明](../variants/emmc/README.md) 完成该步骤，再完成正常 AOSP
产品构建及重建指南第 6 节的校验宿主工具构建。
之后在项目 `tvbox-port/` 的父目录准备 FAT 内容：

```bash
port_root="$PWD/tvbox-port"
aosp_root="$PWD/aosp"
product_root="$aosp_root/out/target/product/rk3288"
emmc_boot_files="$PWD/boot-files-tvbox-emmc"
mkdir -p "$emmc_boot_files/boot" "$emmc_boot_files/extlinux" "$PWD/tvbox-artifacts"
install -m 644 "$port_root/device/firefly/rk3288/prebuilts/zImage" \
  "$emmc_boot_files/boot/zImage"
install -m 644 "$product_root/ramdisk.img" \
  "$emmc_boot_files/boot/ramdisk.img"
install -m 644 "$port_root/variants/emmc/boot/rk3288-firefly-android.dtb" \
  "$emmc_boot_files/boot/rk3288-firefly-android.dtb"
install -m 644 "$port_root/variants/emmc/boot/extlinux.conf" \
  "$emmc_boot_files/extlinux/extlinux.conf"
```

`boot-files-tvbox-emmc/` 是组装输入，不放进源码目录。`variants/emmc/boot/` 不保存
第二份 zImage，也不通过符号链接引用内核。

以下 helper 使用与 Android 构建相同的容器，提供组装、文件系统和图形校验工具。
在同一 shell 执行：

```bash
image_builder=${FIREFLY_ANDROID_BUILDER_IMAGE:-firefly-android17-builder:20261104}
image_work_root=$(dirname -- "$port_root")
run_image_tool() {
  docker run --rm --init --user "$(id -u):$(id -g)" \
    --volume "$image_work_root:$image_work_root" --workdir "$image_work_root" \
    "$image_builder" python3 "$@"
}

run_image_tool "$port_root/scripts/assemble-sd.py" --boot-medium emmc \
  --product "$product_root" --boot-files "$emmc_boot_files" \
  --idbloader "$port_root/variants/emmc/bootloader/idbloader.img" \
  --uboot "$port_root/variants/emmc/bootloader/u-boot-dtb.img" \
  --simg2img "$aosp_root/out/host/linux-x86/bin/simg2img" \
  --output "$PWD/tvbox-artifacts/firefly-rk3288-tv-android17-emmc-alpha.img"

run_image_tool "$port_root/scripts/verify-sd.py" --boot-medium emmc \
  --image "$PWD/tvbox-artifacts/firefly-rk3288-tv-android17-emmc-alpha.img" \
  --product "$product_root" --aosp "$aosp_root" \
  --boot-files "$emmc_boot_files" \
  --idbloader "$port_root/variants/emmc/bootloader/idbloader.img" \
  --uboot "$port_root/variants/emmc/bootloader/u-boot-dtb.img" \
  --simg2img "$aosp_root/out/host/linux-x86/bin/simg2img" \
  --manifest "$PWD/tvbox-artifacts/firefly-rk3288-tv-android17-emmc-alpha.img.json" \
  --report "$PWD/tvbox-artifacts/emmc-image-validation.json"
```

组装和独立校验都会按介质核对 DTB、唯一的 Android bootdevice 参数及实际
U-Boot `bootcmd`。eMMC 还检查 idbloader 内有效 FDT 的
`/chosen/u-boot,spl-boot-order`，要求唯一且只含 `/mmc@ff0f0000`。
这项检查覆盖 SPL 读取第二阶段 U-Boot 的介质选择。

sidecar 清单和独立报告记录 `boot_medium`、`boot_device`。独立校验接受旧版
未写介质字段的 TF sidecar，并按 `sd` 处理；eMMC 必须显式标明 `emmc`。

## 源码包

源码白名单包含 `variants/`、频道重建工具 `tools/` 和测试及 fixtures `tests/`。
默认源码包不含启动二进制；
`--include-prebuilts` 要求原有 TF 内核、DTB、两个加载器和 eMMC DTB、两个
加载器全部存在。可再生的 SPL DTB 记录也仅在该模式下加入。

两种模式均排除 `variants/emmc/out/` 的独立源码解压树、下载和构建输出，
以及重复的 `variants/emmc/boot/zImage`。完整上游源码归档继续使用原有
`kernel/downloads/` 和 `bootloader/source/` 中的单份文件。

`scripts/test-boot-media.py --report REPORT.json` 使用当前 TF 文件和临时的
eMMC/SPL/source-tar fixture 检查介质错配拒绝及源码白名单。实际 eMMC 启动
产物的检查另存于该变体的构建记录。电视版完整整盘报告使用工作根的
`tvbox-artifacts/image-validation.json` 和 `tvbox-artifacts/emmc-image-validation.json`；
频道、媒体、遥控与家长模式的检查索引见 `records/README.md`（本地历史证据：`records/README.md`，未随源码发布）。
