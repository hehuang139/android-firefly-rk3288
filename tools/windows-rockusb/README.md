# Firefly-RK3399 首次整盘烧录准备

这里提供独立的 Windows 只读探测器、协议核心和离线测试。**未在真板执行 USB 操作，真实写入命令行尚未接通。** `rockusb_core.py` 的模拟测试不能当作烧录成功。镜像构建完成、设备容量确定、完整写入与回读成功、冷启动成功是四个不同的验收阶段。

## 当前工具

- `readonly_probe.py` 默认只核对本地 loader 文件。只有显式 `--probe` 才打开 Windows RockUSB 驱动；仅执行设备描述符查询和存储读取。
- `rockusb_core.py` 提供协议构造与依赖注入的写入/回读核心，当前没有真实写入后端或 CLI。默认只比较，写入要求匹配镜像与目标的确认字符串及会话证据。
- `test_offline.py` 使用内存模拟设备，导入模块、测试和默认本地校验都不访问 USB。
- `loader-reference.json` 与 `source-manifest.json` 记录固定来源和哈希。本目录不分发上游源码或 loader 二进制。

在本目录运行离线测试：

```powershell
python -m unittest -v test_offline
```

仅核对本地 loader（目录内需有 loader 和 `usb-loader-manifest.json`）：

```powershell
python readonly_probe.py --loader-dir 'USB-Loader'
```

后续首次只读探测的接口如下；路径与端口必须来自本次新板连接，关闭占用该设备的 RKDevTool 后使用：

```powershell
python readonly_probe.py --loader-dir 'USB-Loader' --probe --hub-path '<本次板卡的 USB Hub 路径>' --hub-port <端口号> --report '<新的 JSONL 文件>'
```

该程序不下载 loader、不写存储、不擦除、不重启、不访问 RAM，也不自动重试。Windows 驱动端点和同步 I/O 兼容性仍需首次实板确认；驱动同步调用不提供已经实测的有界超时承诺。

## 一次连接内完成的首刷流程

准备工作全部完成后才进入此流程。保持新板、独立电源和 OTG 接线不变；准备阶段不反复要求断电或下载。

1. 确认实体为原版 Firefly-RK3399、目标是板载 eMMC、只连接这一块 Rockchip 刷机设备。按该板经过确认的方式进入 **MaskROM**，保存模式、设备和接线记录。单独显示 `LOADER` 不能作为这一项证据。
2. 核对固定 loader 的完整 SHA256。在确认的 MaskROM 会话中，用官方工具执行一次 **仅下载到 RAM 的 Boot 下载**。官方 `rkdeveloptool db` 正是初始化 DDR 并运行 usbplug 的流程；保存命令/操作、loader 哈希和成功日志。不要用写 loader、更新固件或擦除来代替 RAM 下载。
3. 保持该 usbplug 会话，不按 Reset、不掉电、不更换板卡。读取芯片、eMMC 标识和**精确的 512 字节扇区总数**，并完成低、中、高、末尾地址的小样本读取。记录下载后的重新枚举信息；后续如果异常断连、复位或出现新的固件会话，停止并重新建立这组证据。
4. 用已经独立验证的 12 GiB 基础候选、基础 manifest、验证报告和实板扇区数，运行项目 `scripts/prepare-rk3399-target.py`，生成**与此块 eMMC 容量完全相等**的普通镜像文件。该步骤只改本地文件，不碰设备。
5. 核对目标镜像报告为 `PASS_TARGET_FILE_NOT_FLASHED`，文件字节数等于实板扇区数 × 512，完整 SHA256 与报告一致。确认主/备 GPT CRC、备 GPT 位于真实盘尾、旧备 GPT 已清除、七个分区及数据保持不变。大于基础镜像的新增区域全部写零，避免旧系统残留盘尾 GPT。
6. 在同一已确认的官方 usbplug 会话中，通过明确支持**原始物理 LBA 写入**的接口，从 LBA 0 写完整目标镜像；随后重新读取从 LBA 0 到设备最后一个扇区，保存完整回读文件并核对长度、完整 SHA256 和盘尾 GPT。任何失败都不能标记完成，也不能仅凭进度条成功放行。
7. 全部通过后才进行一次正常冷启动，检查串口、画面及启动结果。整盘字节校验成功不能代替启动验收。

精确容量小于 25,165,824 扇区时拒绝写入；不要从显示的整数 MB/GB 倒算扇区数。当前目标文件生成器支持上限 268,435,456 扇区（128 GiB）。输出文件和完整回读文件都需要足够的主机空间。

目标文件生成命令（占位符必须换成本次真实文件和精确十进制容量）：

```text
python scripts/prepare-rk3399-target.py --base-image candidate.img --base-manifest candidate.img.json --verification candidate-verify.json --target-sectors EXACT_DECIMAL_512_BYTE_SECTOR_COUNT --output target-emmc.img
```

输出 `target-emmc.img.json` 绑定基础文件、manifest、验证报告的 SHA256，并记录目标长度、完整哈希和分区/GPT检查。容量未知时不产生目标镜像，更不能写入。

## 何时可以使用官方整盘写入

**不需要先完成未知 RAM 地址的指纹探测，才能使用官方文档规定的 usbplug 写盘流程。** 足够实用的会话依据是：已确认 MaskROM → 本次固定哈希官方 loader RAM 下载成功 → 下载后连续的 usbplug 会话 → 唯一新板与 eMMC/容量读取正常 → 最终目标镜像已验证。这里的依据来自实际执行记录与官方协议语义，并不来自手工修改几个布尔值。

官方 `rkdeveloptool` 的参考命令如下，面向已具备该工具及 USB 接入条件的主机；这是维护者参考流程，**不是已经验证的 Windows RKDevTool 界面步骤或自动脚本**。应逐项检查返回结果；当前文档未执行这些命令。

```text
rkdeveloptool ld
rkdeveloptool db rk3399_loader_v1.30.130.bin
rkdeveloptool ld
rkdeveloptool rid
rkdeveloptool rfi
```

`rfi` 输出的 `Flash Size: ... Sectors` 提供精确扇区数。还需核对存储为 eMMC；有多个可选介质或身份不明时先停止。生成并验证全容量目标文件后，才进入以下写入与完整读取：

```text
rkdeveloptool wl 0 target-emmc.img
rkdeveloptool rl 0 EXACT_DECIMAL_512_BYTE_SECTOR_COUNT readback-emmc.img
```

`wl` 与 `rl` 的地址、长度单位都是 512 字节扇区。使用同一台主机核对两个文件的字节长度与完整 SHA256；例如 Windows 可使用 `Get-Item` 和 `Get-FileHash -Algorithm SHA256`，Linux 可使用 `stat` 和 `sha256sum`。官方 `wl` 自身不会替我们完成完整回读，因此不能省略 `rl` 和文件核对。官方顺序写入也没有本目录模拟核心“首块最后写”的策略，不将两者混为一谈。

在 Windows 上，RKDevTool 的 Boot 行可用于经过确认的 RAM Boot 下载，但整盘写入必须使用已经核实地址语义的 raw-LBA 接口。**当前独立 Python 包不提供此真实写入入口，也没有验证 RKDevTool 某个 GUI 操作可直接写本项目的完整 raw 镜像。** 不把 raw 镜像当作 Rockchip `update.img` 或单个分区文件。集成方须先验证所选 Windows 写入路径，或在支持官方 `rkdeveloptool` 的主机完成上述流程。

## 只读报告的边界

探测器要求唯一驱动接口、VID:PID 为 `2207:330c`，指定 Hub 端口描述符保持一致，EMMC 标记与 eMMC 存储位一致，并严格校验每个 CSW 的签名、标签、状态和 residue。它记录采样哈希及全 00/FF/CC 标志；异常直接停止，报告独占创建。

PID 不能证明板型，EMMC 标记不是唯一 CID，样本不能证明整盘健康。探测器不知道操作者此前实际下载了什么，因此成功报告保留 `active_loader_verified=false` 和 `physical_lba_verified=false`。这不否定上面可核对的官方会话流程；它表示该程序**单独运行**没有采集到那部分证据。不得通过手工把 false 改为 true 放行自制写入器。

首次 Windows 探测还要确认 Hub/接口对应关系及驱动兼容性。不会把另一块板的容量、USB 端口、RAM 地址、补丁或异常兼容规则带到新板。

## 模拟写入核心的离线验收

当前 21 项测试覆盖默认只读、错误 PID、容量不足、错误镜像、缺少确认或映射证据、短尾块、即时及最终校验错误、写后断连、源文件变化、非零 residue 拒绝、越界及无真实写入 CLI。核心先做完整源哈希，分块即时回读，再做第二次完整顺序读取和字节/SHA核对。它是后续集成材料，没有实板验证结果。

通用核心允许镜像小于介质，并明确报告未验证剩余尾部；**本项目首次整盘安装流程不使用这一模式**，只接受与实板容量相等的目标文件和完整介质回读。

## 来源与许可

本目录独立 Python 实现及说明按 MIT 许可提供，见 `LICENSE`。上游协议源码只用于交叉核对，未复制到此分发目录，仍按各自上游许可证使用。

- [官方 rkdeveloptool 固定源码](https://github.com/rockchip-linux/rkdeveloptool/tree/304f073752fd25c854e1bcf05d8e7f925b1f4e14)：`RKComm.cpp` 的 ReadLBA/WriteLBA 原样发送扇区地址；`main.cpp` 定义 `db`、`wl`、`rl`、`rfi` 行为。逐文件 URL/哈希见 `source-manifest.json`。
- [官方 Rockusb 文档](https://opensource.rock-chips.com/wiki_Rockusb)：区分 MaskROM、usbplug 与旧 miniloader，说明 `db` 进入 usbplug；不能把旧固件提供的下载模式直接当作本次 usbplug 会话。
- loader 固定在 rkbin 提交 `3e288fe814e059dd06833495f845cab04ac20a5c`，文件 `rk3399_loader_v1.30.130.bin`，454,990 字节，SHA256 `1d2330a5eb5f638c7533464ca57018754157e65daf391e4f544befdd2b653929`。它是 RAM DDR/usbplug 下载候选，未在本次新板验证；不是要单独写进 eMMC 的 idbloader。来源见 `loader-reference.json`。
