> Historical bring-up reference. For the final tested eMMC source profile and
> current validation limits use BUILD.md and docs/移植复盘.md. Old check counts
> and TF/HEVC instructions below are not current release validation.

# 原版 Firefly-RK3288：TF 卡首启

本指南对应原版 `firefly,firefly-rk3288`，使用 TF 卡、HDMI、USB 键鼠和以太网。
Firefly-RK3288 Reload、Plus 及其他 RK3288 板卡需要各自的设备树。
电视版整盘和报告位于工作根 `tvbox-artifacts/`。本轮完整 `droid` 已通过，TF
整盘独立检查为 518/518；其余打包状态见 `build-status.json`，eMMC 结果见
`emmc-image-validation.json`，最终哈希见 `SHA256SUMS`。快速刷卡见
[TF 卡刷写与 HDMI 首启](tf-install.md)。

RK3288 的 BootROM 优先检查有效 eMMC 启动项，随后才检查 SD/TF。当前板载系统
和加载器未知，尚无经过本项目验证的无写入切换流程；TF 镜像写入正确也不保证
上电时执行它。官方流程及证据见 [启动介质选择](boot-selection.md)。

需要安装到板载存储时，另见 [eMMC 安装说明](emmc-install.md)。它要求至少
12 GiB 实际用户区、确认现有 Loader 地址映射并先备份，使用独立 eMMC 变体。

## 1. 准备镜像和接线

准备至少 **16 GB 的 TF/microSD 卡**、读卡器、板卡适配的独立电源、HDMI 显示器、
USB 键盘和鼠标。建议先使用普通 1080p 显示器、直连 HDMI 线及有 DHCP 的路由器。
若要收集日志，电脑还需安装 Android 官方 Platform-Tools，并准备可传数据的
Micro-USB 线；只有充电功能的线不能用于 ADB。

整盘镜像名为：

```text
firefly-rk3288-tv-android17-sd-alpha.img
```

它是 **12 GiB 的整盘镜像**，包括分区表、加载器和 Android 分区。
balenaEtcher 可直接选择 `.img.xz`；使用仅接受原始镜像的工具时，先完整解压
得到 `.img`，电脑需留出至少 12 GiB 空间。按交付校验和核对实际使用的文件。

本版的连接用途如下：

| 板卡接口 | 接什么 | 用途 |
| --- | --- | --- |
| TF/microSD 卡槽 | 写好整盘镜像的 TF 卡 | 被选中后加载 Android 并保存数据 |
| HDMI | 显示器 | Android 桌面和授权提示 |
| USB host，普通 USB-A 接口 | 键盘、鼠标；需要时接供电 USB hub | 操作界面 |
| 标有 OTG 的 Micro-USB 接口 | 数据线连接电脑 | USB ADB 调试 |
| RJ45 | 路由器或交换机 | 有线网络 |
| 板卡电源接口 | 适配的独立电源 | 给开发板供电 |

OTG 在当前设备树中固定为设备模式，不能通过 OTG 转接头接键鼠。
USB-A host 接口也不能替代 OTG 接电脑调试；不要用 USB-A 对 USB-A 线连接电脑。
板卡仍使用独立电源，不依靠电脑的 OTG 连接供电。

## 2. 写入 TF 卡

1. 备份 TF 卡中的文件。刷写会覆盖该卡原有的全部分区和数据。
2. 用读卡器接入电脑，打开 balenaEtcher 等支持整盘镜像并带写后校验的图形工具。
3. 选择 TF 版 `.img.xz`（Etcher）或已解压 `.img`，按容量和设备名称确认目标为 TF 卡，然后开始写入。
4. 等待写入及校验全部完成，再安全弹出读卡器。

不需要预先分区、格式化，也不要把 `.img` 当普通文件复制到卡里。
Android 的 ext4 分区在 Windows 中可能出现格式化提示，取消即可。
本方案的 TF 卡使用整盘写入，不单独刷 `boot.img`；启动选择需另按下一节核对。

插入更大容量的卡时，当前整盘布局仍为 12 GiB，`userdata` 约 5.2 GiB；
额外卡空间不会自动扩容。首启先保持原分区布局。

## 3. 冷启动

这次检查用于观察现有启动环境是否会执行 TF 镜像；冷启动不会改变 ROM 的
启动介质优先级。完成写后校验后，先做一次以下检查。

1. 板卡完全断电，插入 TF 卡。
2. **先接好 HDMI 并打开显示器，选中对应 HDMI 输入**，让内核启动时能读取 EDID。
3. 键盘、鼠标接 USB host，网线接 RJ45；要用 ADB 时，把 OTG 数据线接电脑。
4. 接通板卡独立电源，正常开机。首次排查先留出 10 分钟，并记录画面变化及时间。

先观察显示器是“无信号”、已有文字、Android 动画，还是进入桌面。
本版跳过设置向导，默认进入 Firefly TV；先用 USB 键鼠确认主页、设置和播放器入口。
若出现的是原来的旧系统界面，记录系统名称、版本、能够取得的启动日志和
bootloader 版本，再断电保存现象及 TF 写后校验结果。有效 eMMC 的优先级高于
TF；是否能随后加载 TF，取决于现有 eMMC 加载器。不要仅因进入旧系统就反复
重写已校验的 TF 卡，Recovery 也不是强制选择 SD 的方法，不要因此刷写或擦除
eMMC。当前需要先确认既有启动环境，不能把此现象直接判定为 TF 镜像损坏。

首启配置使用 Mesa/Panfrost 图形栈，HDMI 模式由显示器 EDID 选择。
当前没有为 Wi-Fi、蓝牙配置 Android HAL/固件集成。电视版已加入 HDMI 音频 HAL
和 CEC/红外遥控组件；首启先用网线、USB 键鼠检查画面与输入，再播放内置测试片
检查声音及硬件解码，记录 HDMI/电视型号和检查结果。

系统没有 GApps、Google Play 或 Google 登录向导。它是 `userdebug` 开发系统，
`userdata` 未加密、SELinux 为 permissive、AVB 关闭，KeyMint/Gatekeeper 使用
软件实现。刷卡调试阶段使用测试账号和测试数据。

## 4. 连接 ADB 并授权

在电脑的 Platform-Tools 目录打开终端；以下示例中的 `adb` 需在 `PATH` 中。
Windows PowerShell 在该目录可把命令开头改为 `./adb.exe`。

```sh
adb devices -l
```

当前配置默认请求 USB ADB，保留电脑密钥认证，没有开启网络 ADB。
第一次连接若显示 `unauthorized`，用 HDMI 上的界面和鼠标接受“允许 USB 调试”
提示。只对自己的电脑勾选“始终允许”，然后再次执行上面的命令。

| `adb devices -l` 结果 | 下一步 |
| --- | --- |
| 序列号后为 `device` | 可以执行下面的日志命令 |
| `unauthorized` | 在板卡界面接受授权；未出现提示时重新插拔 OTG 数据线 |
| `offline` | 等待系统继续启动，重新插拔 OTG；仍不恢复时重启电脑侧 ADB 服务 |
| 没有设备 | 检查是否接 OTG、数据线、电脑 USB 接口及板卡供电 |
| `no permissions` | 修复 Linux 电脑上的 Android USB/udev 权限后重新插拔 |

Windows 若已识别到 USB 设备但没有 ADB 接口，在设备管理器检查 Android ADB
驱动；若显示器上已有桌面，亦可在“设置 → 关于设备”连续点击版本号启用
开发者选项，再检查“系统 → 开发者选项 → USB 调试”。

`offline` 等电脑侧异常可先执行：

```sh
adb kill-server
adb start-server
adb devices -l
```

没有授权成功前，网线不能代替 USB 调试；本版没有预置 ADB 的 TCP 监听端口。
不要把电脑显示的 Rockchip Loader/Maskrom 设备当成 Android ADB，它属于更早的
下载模式。

## 5. 保存最少的首启日志

设备状态为 `device` 后，在电脑新建的日志目录中运行：

```sh
adb shell getprop > getprop.txt
adb shell uname -a > kernel-version.txt
adb logcat -b all -d > logcat.txt
adb shell dumpsys SurfaceFlinger > surfaceflinger.txt
adb shell ip address > ip-address.txt
adb shell ip route > ip-route.txt
adb shell dumpsys ethernet > ethernet.txt
```

`getprop.txt` 用于检查版本和启动进度：当前目标为 Android 17、SDK 37、
`ro.hardware=fireflyrk3288`，`sys.boot_completed=1` 表示框架已完成启动。
SurfaceFlinger 输出用于查看实际显示设备和 EGL renderer；网络输出用于查看
以太网接口、DHCP 地址及默认路由。

需要内核日志时，`userdebug` 可尝试重启 adbd 为 root。它会短暂断开 USB：

```sh
adb root
adb wait-for-device
adb shell dmesg > dmesg.txt
```

如果 `adb root` 报错，保存其原文并先保留已取得的普通日志。
不要先清空 logcat、恢复出厂设置或重刷卡，否则会丢失本次问题的线索。
若连接了多台 Android 设备，将每条命令开头的 `adb` 改为 `adb -s 实际序列号`。

## 6. 按现象排查

| 现象 | 先做什么 |
| --- | --- |
| HDMI 一直无信号 | 断电后重接 HDMI，先开显示器再给板卡供电；换直连线、1080p 显示器和 HDMI 输入；复查 TF 写后校验及电源 |
| 进入原来的旧系统 | 保存旧系统及 bootloader 信息、画面和 TF 写后校验结果；按启动介质选择文档继续确认 eMMC 加载器的 TF 支持 |
| 出现文字后停住 | 拍下最后一屏和上电后经过的时间；检查 ADB 是否出现；不要只记录电源灯颜色 |
| 有 Android 动画但迟迟没有桌面 | 检查 ADB 并保存 `getprop`、`logcat`；查看 `sys.boot_completed` 和图形服务日志 |
| 桌面黑屏，但 ADB 为 `device` | 保存 `surfaceflinger.txt`、`logcat.txt` 和 `dmesg.txt`，保留显示器型号及 HDMI 接法 |
| 键鼠无反应 | 确认插在 USB host，先直连单个普通有线键鼠；再试另一 host 口，使用 hub 时检查供电 |
| 接网线仍不能上网 | 先看网口链路灯、换线和路由器 LAN 口；检查路由器 DHCP，再保存 IP、路由及 Ethernet 日志 |
| 持续重启、显示和 USB 反复断连 | 先换适配电源与可靠 TF 卡；记录重复间隔并保存能取得的日志 |

已连上 ADB、需要进一步判断 USB 或输入时，可补充：

```sh
adb shell getprop sys.usb.controller
adb shell getprop sys.usb.config
adb shell getprop sys.usb.state
adb shell ls /sys/class/udc
adb shell dumpsys input > input.txt
```

配置选择的 OTG 控制器是 `ff580000.usb`，目标 USB 功能为 `adb`。
有线网优先接带 DHCP 的普通路由器；“已获得局域网地址”和“能访问互联网”
分开检查，不能仅凭网口灯亮判断 Android 已联网。

若 HDMI 没有可辨认画面、电脑也没有出现可授权的 ADB，当前这两条入口还取不到
早期启动日志。保存 TF 写入校验结果、板卡正反面照片、显示器现象和电脑 USB
识别信息；后续定位加载器或早期内核问题时，再使用 3.3 V USB 转 TTL 串口。
首轮不需要购买串口工具，也不需要为了尝试启动而修改 eMMC。

反馈时附上镜像文件名及 SHA-256、板卡型号、TF 卡容量、电源规格、显示器型号、
从上电到故障的时间、画面照片、`adb devices -l` 结果和取得的日志，方便把问题
定位到刷卡、加载器、内核、Android 框架或显示输入环节。

配置依据：`boot/extlinux.conf`、`device/firefly/rk3288/{BoardConfig.mk,device.mk}`、
`device/firefly/rk3288/init/` 和 `kernel/rk3288-firefly-android17.dts`。
