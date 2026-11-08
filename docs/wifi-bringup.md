# 原版 Firefly-RK3288 Wi-Fi 接入与验证

2026-11-08：原版板的软件重启验证已完成，`wlan0`、固件、`wificond` 和
supplicant 能自动启动，Android 框架实际扫描到 8 个热点，其中 6 个在
2.4 GHz、2 个在 5 GHz。没有连接热点，没有验证密码认证、DHCP、默认路由、
断线重连或冷断电首启。本文描述的是这次最小 station 接入，不是完整无线认证。

## 四层缺失与处理

| 层次 | 实际问题 | 本次处理与边界 |
|---|---|---|
| 板级 SDIO | 最终 DT 没有恢复可用的内部 SDIO 描述；补齐后初次枚举仍出现 `-84` | 在既有最终 DT 上追加原版板 delta；允许一次只针对 `ff0d0000.mmc` 的受限重新绑定 |
| 内核与固件 | 最终内核启用了模块构建，但产品未带齐匹配模块、固件和校准输入 | 导出六个 matching modules，校验导入 CRC；按固定散列获取固件并保留许可 |
| Android 原生服务 | 未完整安装 supplicant、依赖和真实 `wificond`；`/system/bin/wificond` 只是悬空链接 | 构建 AOSP AIDL V5 supplicant、真实 `system_ext/bin/wificond` 及各自 RC/依赖 |
| 框架与产品配置 | feature、启动集成和框架选路不完整；当前默认走迁移后的直接 NL80211 路径 | 加入 station feature 和 init；用单项静态 RRO 选择已验证的 `wificond` 路径 |

`/system/bin/wificond` 文件名存在不代表进程可执行：它的目标
`/system_ext/bin/wificond` 当时并不存在，init service 也未定义。
`PRODUCT_PACKAGES += wificond` 现在让 AOSP 模块安装真实 daemon 和源 RC。
supplicant 使用 NL80211 和 AIDL；私有驱动命令的 stub 不替代内核 Wi-Fi 驱动。
本接入没有引入不匹配的 `bcmdhd` HAL，也没有宣告 IWifi vendor HAL。

## 框架选路为什么需要 RRO

这个 AOSP 版本的 `wificond_to_nl80211_migration` aconfig 标志与
`config_wificondMigrationEnabled` 资源默认开启。`WifiInjector` 构造时决定
使用 `Nl80211Native` 的直接路径还是 `wificond` 路径；如果
`init.svc.wificond` 未定义，即便资源设为 false，也会强制选择迁移路径。
之后才启动 daemon 不会改变已创建对象的选择。

`FireflyWifiOverlay` 是 vendor 静态 RRO，只将
`com.android.wifi.resources:bool/config_wificondMigrationEnabled` 设为
false，目标 overlayable 为 `WifiCustomization`。必须把真实 daemon、RC
与 RRO 一起安装，在新的 SystemServer 创建 Wi-Fi 服务前生效。
第二次软件重启后已读回资源为 false，`wifinl80211` 与
`android.hardware.wifi.supplicant.ISupplicant/default` 均存在。

## 内核、DT 与有限恢复

内核版本为 `6.18.60-firefly-tvbox`。六个模块是 `cfg80211`、`brcmutil`、
`brcmfmac` 以及其 `wcc`、`cyw`、`bca` 三个实现模块。
`scripts/prepare-wifi-kernel.py` 检查完整配置 SHA256、release、ELF32 ARM、
vermagic 与本次 `Module.symvers`；本次实际检查了 517 个导入 CRC。
同一流程回编译原基线 DT 与追加 SDIO delta 后的 DT，两个结果均匹配固定散列。
DTC 仍有反编译树的警告，散列匹配不等于通过 DT schema 验证。

原构建目录里的旧模块 release 与正在运行的最终内核不同，因此本次重新构建
匹配模块。brcmfmac 的异步固件回调还可能动态请求实现模块，而实机没有可用的
module helper；准备脚本先暂停 SDIO 自动探测，注册全部模块，再恢复探测，
避免仅靠连续 `insmod` 时序碰巧成功。

`firefly-wifi-prepare.sh` 在 `post-fs-data` 阶段运行，服务超时为 30 秒。
它先等待内部 SDIO function 2；若没有任何 SDIO 卡、启动分区与 host 映射
都符合本板记录，才对 `ff0d0000.mmc` 做一次 unbind/bind。它不处理 eMMC
控制器；发现未知卡、部分枚举、错误 host/启动映射或恢复后仍失败就退出，
没有无限重试。随后按依赖顺序加载模块并恢复 SDIO 自动探测设置。

第二次软件重启记录中，启动约 3 秒时仍有 `-84`；受限恢复发生在 16.90 秒，
18.08 秒 SDIO 枚举成功，19.95 秒报告 `BCM4339/2` 固件
`6.37.39.113` 就绪。随后有真实双频扫描结果。这个实验证明有限恢复在该次
软件重启中有效，不能证明最早的电源、复位或总线时序问题已经修复。

## 固件、校准与许可

固定下载源和散列位于
`device/firefly/rk3288/wifi/firmware-sources.json`。

- 4335 固件来自固定 Ubuntu `linux-firmware` 包的 Broadcom 文件。
- 4339 实际来自包内 `cypress/cyfmac4339-sdio.bin`；原构建机 Broadcom
  文件名是符号链接。获取器以驱动请求的名称保存内容，同时保留 Cypress 许可。
- `regulatory.db` 与签名来自固定 `wireless-regdb` 包；不绕过签名或地区限制。
- NVRAM 优先使用自己模块适用的校准文件。固定 Radxa AP6335 模板只允许显式
  选择本地验证；其重新分发权限未确认，内容不进入源码仓库。没有生成通用 MAC
  或修改 RF 校准值。本板实际报告 OTP 地址，`addr_assign_type=0`。

当前固件还报告缺少可选 `clm_blob`/`txcap_blob`；本次已有扫描结果，但不能
从几个频道推断所有地区/频段完整支持。不要用另一模块的校准文件掩盖差异。
获取器保留固件许可，源码归档排除整个 `prebuilts` 目录。

## 构建与验收

按 [BUILD.md](../BUILD.md#21-wi-fi-firmware-and-matching-modules) 先构建匹配
内核和模块，再准备固件，然后执行原 `install`、`graph`、`build` 流程。
`build.sh kernel` 将同一 Wi-Fi DTB 同时放入 eMMC 与 Android boot 输入，
并把模块放入设备的本地 prebuilts。固件获取输出目录默认与产品复制规则一致。

构建后应核对实际安装的 supplicant、AIDL V5 VINTF fragment、唯一 service RC，
以及 `system_ext/bin/wificond` 和它的 RC。运行依赖必须是真实实现库，不能把
Soong LLNDK 编译 stub 放入运行分区。已部署候选的 supplicant 运行依赖审计
覆盖 28 个 ELF / 144 条依赖边，wificond 覆盖 23 个 ELF / 114 条依赖边。

公开 [验证记录](validation/wifi-bringup-20261108.json) 只保留计数、状态、
通用硬件属性和散列；不包含 SSID、BSSID、MAC、密码、ADB 身份或原始网络日志。
私有候选的分项构建、模块导出与固件提取已执行；公开树整套干净 Android
产品构建和新整盘镜像重刷未在这轮完成。

当前只声明 `android.hardware.wifi`。热点、P2P、Passpoint、Bluetooth、
低功耗、漫游、长期吞吐与 SELinux enforcing 都不在已验证范围内。
有线连接期间显示 Wi-Fi 配置的 TvSettings 修正见
[设置页修复](tvsettings-repair.md)，设置入口可用与真正连接成功仍需分别验收。
