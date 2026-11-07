> 历史 bring-up 资料。当前构建与验收范围以 [BUILD.md](../BUILD.md) 和独立移植复盘为准。旧 alpha、TF、HEVC 与旧校验项不代表当前发布已验证状态；当前 HEVC 硬件节点停用，最终板上验收介质为 eMMC。

# 原版 Firefly-RK3288：eMMC 安装

电视版的 eMMC 整盘产物位于工作根的
`tvbox-artifacts/firefly-rk3288-tv-android17-emmc-alpha.img`，压缩文件追加 `.xz`。
本轮构建及打包状态见 `tvbox-artifacts/build-status.json`，整盘独立检查结果见
`tvbox-artifacts/emmc-image-validation.json`，文件哈希见同目录 `SHA256SUMS`。
安装前先确认这些步骤已完成。当前板载 Loader 尚待识别；先用
[TF 首启指南](tf-install.md) 跑通 HDMI 入口，再按本文检查 eMMC 安装条件。

eMMC 变体使用 `ff0f0000.mmc`，配套文件位于 `variants/emmc/boot/` 和
`variants/emmc/bootloader/`；TF 变体使用 `ff0c0000.mmc`。加载器、设备树和
extlinux 配置须一起匹配启动介质。

## 1. 先确认容量、镜像和现有加载器

目标 eMMC 的实际用户区容量必须至少为 **12,884,901,888 字节**，即
**25,165,824 个 512 字节扇区**。通常需标称 **16 GB 或更大**的 eMMC；
8 GB 型号放不下本布局。以设备实际报告的扇区数为准，不按板卡销售名称判断。

eMMC 整盘镜像文件名为：

```text
firefly-rk3288-tv-android17-emmc-alpha.img
```

从 `tvbox-artifacts/` 取得镜像，复制到运行 `rkdeveloptool` 的目录。
使用生成记录及 SHA-256 核对文件，压缩包须先解压。它是包含 GPT、加载器、
FAT 启动文件和 Android 分区的原始整盘，不能替换成单个 `boot.img`、
Android sparse 分区镜像或 `update.img`。

安装会覆盖 eMMC 用户区的前 12 GiB，包括原启动加载器、分区表及该范围内的
系统和数据。先备份下文所述的整个 eMMC 用户区；本布局不会自动使用 12 GiB
以外的容量。电脑文件系统需支持大于 4 GB 的文件，并留出至少“eMMC 实际
用户区容量 + 24 GiB”的空间，以保存备份、解压后的镜像及写后回读文件。

**现有 Loader 的地址映射必须已确认。** `rkdeveloptool ld` 显示 `Loader`
只说明当前 USB 下载模式，不能证明扇区 0 就是物理 eMMC 用户区的扇区 0。
Rockchip 官方 [Rockusb 文档](https://opensource.rock-chips.com/wiki_Rockusb)
指出，部分旧 Miniloader 的 `wl` 地址会额外加 `0x2000`，且前面的启动区域不能
通过该接口直接写入。未知加载器下不能执行本文的整盘备份或 `wl 0`。

只有已确认目标为 eMMC、`rl` / `wl` 采用完整用户区物理 LBA 直映射的 Loader，
才适用后面的备份与安装步骤。当前板载加载器未知；先完成第 3 节的识别并保存
信息，后续再确定其支持情况。不能仅凭容量正确或显示 `Loader` 就进入写入步骤。

安装前还需保存一条能够再次进入下载接口的实际路径、当时的完整用户区备份和
精确总扇区数。下文第 6 节列出的新 U-Boot 恢复入口已有配置和源码依据，
HDMI 画面、USB 键盘及 OTG 枚举仍需在板上观察；它不能替代当前 Loader 的
识别，也不能在覆盖旧系统前被当作已经验证的恢复手段。

## 2. 使用固定版本的电脑工具

本文命令按官方 [rockchip-linux/rkdeveloptool](https://github.com/rockchip-linux/rkdeveloptool/tree/304f073752fd25c854e1bcf05d8e7f925b1f4e14)
提交 `304f073752fd25c854e1bcf05d8e7f925b1f4e14` 核对；其 Autotools 版本号是
`1.32`。以下示例使用 64 位 Linux 电脑与 Bash，在工具源码目录运行
`./rkdeveloptool`，避免误用同名的其他版本。

按该版本的 `Readme.txt` 准备构建依赖后：

```sh
git clone https://github.com/rockchip-linux/rkdeveloptool.git
cd rkdeveloptool
git checkout --detach 304f073752fd25c854e1bcf05d8e7f925b1f4e14
./autogen.sh
./configure
make
./rkdeveloptool --version
./rkdeveloptool --help
```

上游列出的 Debian/Ubuntu 依赖包括 `libudev-dev`、`libusb-1.0-0-dev`、
`dh-autoreconf` 和 `pkg-config`，还需 C++ 编译工具。电脑侧 USB 权限应按
该源码中的 `99-rk-rockusb.rules` 配置；权限错误不能通过换刷写参数解决。

## 3. 通过 OTG 识别当前模式

1. 先保存旧系统能够取得的版本、启动日志及加载器信息。完全断电后拔出 TF，
   以便确认后续访问的是板载存储。
2. 用可传数据的 Micro-USB 线将板卡 **OTG** 口接到电脑，板卡使用合适的独立
   电源。USB-A host 口不能代替 OTG 接电脑。
3. 通过当前板卡固件已有的 Loader 入口进入 Rockusb。Rockchip 的通用文档列出
   上电按 Recovery/volume+，或受支持系统中的 `reboot loader`；具体入口由现有
   固件决定，本项目尚未验证用户板卡的按键操作。以电脑实际识别结果为准。
4. 电脑只连接这一台 Rockusb 设备，先运行：

```sh
./rkdeveloptool ld
```

保存完整输出，包括 VID、PID、LocationID 和模式。RK3288 的官方 Rockusb
VID/PID 为 `2207:320a`。出现多台设备、`Unknown` 或找不到设备时，先停止排查
连接和权限；不按序号猜目标。

| `ld` 的模式 | 当前可做的事 |
| --- | --- |
| `Loader` | 已进入加载器提供的 USB 下载接口；继续读取信息，仍需确认具体加载器及 eMMC 地址映射 |
| `Maskrom` | BootROM USB 模式；本指南在此停止，需要另行验证适合原版板的 RAM loader |

本项目 `idbloader.img` 是写在介质上的 **rksd** 格式，不能交给
`rkdeveloptool db`。`db` 接收有对应 DDR/USB 下载入口的 Rockchip loader 包；
当前没有为这块实板验证此类下载包。不要尝试把文件改名后 `db`，也不要擦除
eMMC 或短接引脚来改变模式。

仅当恰好识别到一台 `Loader` 设备时，读取容量并保存原始输出：

```sh
./rkdeveloptool rfi
```

该固定版本同时打印 `Flash Size: … MB` 和 `Flash Size: … Sectors`。
其源码将总扇区数除以 `2 * 1024` 后显示为 `MB`，实际是截断后的 MiB；
**计算和备份使用 `Sectors` 那一行的完整整数**，每扇区 512 字节。
读取失败、容量异常、小于 25,165,824 扇区，或尚不能确认是 eMMC 及其地址映射
时，在此停止，保留 `ld`、`rfi` 输出与原系统信息。

## 4. 备份整个 eMMC 用户区

本节要求已经确认 Loader 的 eMMC 物理 LBA 直映射；这不是确认未知 Loader
映射的方法。`rl 0 N 文件` 中的 `N` 是**实际设备总扇区数**，不能填 12 GiB
镜像的扇区数来替代整机备份。

在同一个 Bash 终端输入 `rfi` 的 `Sectors` 整数并检查容量：

```sh
read -r -p '输入 rfi 的 Sectors 整数: ' emmc_sectors
python3 - "$emmc_sectors" <<'PY'
import sys
value = sys.argv[1]
if not value.isascii() or not value.isdecimal() or value.startswith('0'):
    raise SystemExit('停止：请输入没有前导零的十进制扇区数')
count = int(value, 10)
if not 25165824 <= count <= 4294967295:
    raise SystemExit('停止：容量不足或超出此工具的扇区参数范围')
print(f'eMMC 用户区：{count} 扇区，{count * 512} 字节')
PY
```

检查报“停止”时，不执行后续命令。确认计数与设备输出一致后，使用一个尚不存在
的新备份文件名；`rl` 会覆盖同名文件：

```sh
./rkdeveloptool rl 0 "$emmc_sectors" firefly-rk3288-before-emmc-user.img
```

读取必须成功结束。随后核对文件长度并保存 SHA-256：

```sh
python3 - "$emmc_sectors" <<'PY'
from pathlib import Path
import sys
expected = int(sys.argv[1], 10) * 512
actual = Path('firefly-rk3288-before-emmc-user.img').stat().st_size
if actual != expected:
    raise SystemExit(f'停止：备份长度 {actual}，应为 {expected}')
print(f'备份长度正确：{actual} 字节')
PY
sha256sum firefly-rk3288-before-emmc-user.img > before-emmc-user.SHA256SUMS
sha256sum -c before-emmc-user.SHA256SUMS
```

保留备份、校验文件和当时的设备/Loader 信息。这里的“整个用户区”指 Loader
暴露的 eMMC LBA 区域；`rl` 不会备份独立的 eMMC boot0、boot1 或 RPMB 区域。
备份长度、哈希或读取过程出现错误时，先解决备份问题，不写入新系统。

## 5. 写入并逐字节回读比对

本节只用于已经生成并通过离线校验的 **eMMC** 变体，且第 1–4 节的加载器、
目标容量和完整用户区备份条件均已满足。再次核对解压镜像的发布 SHA-256 及
长度；本布局原始 `.img` 必须为 **12,884,901,888 字节**。

在确认的同一 Loader 会话中，从物理用户区扇区 0 写入：

```sh
./rkdeveloptool wl 0 firefly-rk3288-tv-android17-emmc-alpha.img
```

写入成功后，先保持 USB 和独立电源连接，回读刚写入的全部 12 GiB：

```sh
./rkdeveloptool rl 0 25165824 firefly-rk3288-emmc-written-readback.img
cmp firefly-rk3288-tv-android17-emmc-alpha.img firefly-rk3288-emmc-written-readback.img
```

`cmp` 退出状态为 0 且没有输出表示两文件逐字节一致。工具写入完成的进度文字
不能代替这次回读比对。失败时保留现有 Loader 连接、原始备份和错误输出，先
定位原因；不追加 `ef`、`ul` 或 `gpt` 等命令。

比对成功后，先连接并打开 HDMI 显示器、接上 USB host 键鼠及网线，再重启：

```sh
./rkdeveloptool rd
```

保持 TF 拔出，记录首次启动画面及时间。进入 Android 后，USB 授权、ADB 和
日志收集步骤见 [首启指南第 4–6 节](first-boot.md)。本项目尚未上板，实际
启动结果应另行记录。

## 6. 新 U-Boot 的恢复入口与观察条件

此节对应本项目 eMMC 变体的 `U-Boot 2024.01-firefly-android-emmc1`，不是对
板卡原有未知固件的操作说明。实际 `.config` 与生成二进制已核对：默认先执行
`usb start`，再进入 **5 秒**自动启动倒计时；输入配置为 `serial,usbkbd`，
输出为 `serial,vidconsole`，已编入 USB 键盘、Rockchip HDMI、Rockusb 和
USB Fastboot 支持。

这些配置提供了不用 TTL 的候选入口，但有明确前提：主 U-Boot 已运行、显示器
已取得 U-Boot 画面、USB host 侧键盘已枚举，按键能中断倒计时。操作时先接好
并打开 HDMI 显示器，把普通有线键盘接 USB host，OTG 用数据线连接电脑；
上电后观察 U-Boot 版本和 `Hit any key to stop autoboot`，在倒计时中按空格。
只有实际出现可输入命令的 U-Boot 提示符，才继续。若没有画面或按键无效，
保存现象，不盲输命令；已安装系统能用的 ADB 入口可按下面的单独条件检查。

在确认是上述本项目 U-Boot 的提示符后，先只读查看：

```text
version
mmc list
mmc dev 0 0
mmc info
```

本变体设备树的 `mmc0` 是板载 eMMC；`mmc dev 0 0` 选择其用户区，第二个 `0`
不是 GPT 分区号。保留设备、容量和选择结果，确认没有 MMC 初始化错误。
`mmc info` 的容量是易读显示，不能替代安装前保存的精确扇区数。命令输出与
预期不一致时先停止，不根据此页的设备号操作其他板卡或其他 U-Boot。

需要电脑重新访问 eMMC 时，可在这个已确认的提示符运行：

```text
rockusb 0 mmc 0
```

它启动 USB 控制器 0 的 Rockusb，并把已选中的 eMMC 用户区提供给电脑。
电脑用固定版本的 `./rkdeveloptool ld` 检查是否出现唯一 `Loader` 设备。
该 U-Boot 源码的 `rl` / `wl` 路径把协议 LBA 直接交给选中的块设备；这与
第 1 节中未知旧 Miniloader 的地址平移情况不同，仍须以板上设备识别和实际
读取结果核对连接。

**当前 U-Boot 的 Rockusb 没有实现 `ReadFlashInfo`，因此 `rfi` 在此模式下
不受支持。** 不要为此追加 `db`、`ul` 或擦除操作。此时使用安装前保存的精确
eMMC 总扇区数和用户区备份；缺少该记录时先保留当前接口，不猜容量或改写
存储。确认连接后可先按第 4 节的 `rl` 形式读取并保存现状；使用原完整用户区
备份恢复时，仍需核对备份长度、SHA-256、相同物理目标及实际总扇区数，写后
回读整个备份范围比对，而不是只校验本项目镜像的 12 GiB。

另一个候选入口是在同一提示符运行 `fastboot usb 0`。电脑侧要用 Android
Platform-Tools 的 `fastboot devices` 识别，退出可用 `fastboot reboot`；它与
Rockusb 使用不同协议，不能交给 `rkdeveloptool`。本说明不通过 Fastboot
执行整盘备份或写入。

当前共享内核已编入 `REBOOT_MODE` 和 `SYSCON_REBOOT_MODE`，并同步到两种
镜像的 zImage。`adb reboot bootloader` 对应的重启标志及 U-Boot 路由已通过
配置、设备树和构建产物检查，目标是 **USB Fastboot**。该命令要求 Android
已运行且电脑 ADB 已授权，板上执行及 OTG 枚举结果在首启时记录。最新内核
记录由 `kernel-latest.json`（本地历史证据：`records/kernel-latest.json`，未随源码发布） 索引。
`adb reboot loader` 也不在本 U-Boot 已处理的入口之列。

物理 Recovery 按键不能替代上述判断。当前通用 U-Boot 的下载键检测路径会请求
返回 BootROM/Maskrom；尚无本用户板卡按键接线及实际行为的核实记录。若电脑
显示 Maskrom，按第 3 节停止，不使用介质上的 `idbloader.img` 执行 `db`。
若主 U-Boot 都无法运行，这些 HDMI/键盘和 Android ADB 入口也无法使用，
需先定位早期加载器问题。

固定源码的行号、哈希及命令依据见
`records/emmc-install-source-audit.json`（本地历史证据：`records/emmc-install-source-audit.json`，未随源码发布）。
本节的实际配置、二进制与源码核查见
`records/emmc-recovery-source-audit.json`（本地历史证据：`records/emmc-recovery-source-audit.json`，未随源码发布）。
