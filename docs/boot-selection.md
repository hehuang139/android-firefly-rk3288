> 历史 bring-up 资料。当前构建与验收范围以 [BUILD.md](../BUILD.md) 和独立移植复盘为准。旧 alpha、TF、HEVC 与旧校验项不代表当前发布已验证状态；当前 HEVC 硬件节点停用，最终板上验收介质为 eMMC。

# 原版 Firefly-RK3288 的启动介质选择

RK3288 的 BootROM 先检查有效的 eMMC 启动项，再检查 SD/TF。把本项目加载器
正确写入 TF 卡，并不能保证上电时会执行它。当前板载 eMMC 的系统和加载器版本
未知；本项目尚未刷卡，也尚无经过本项目验证的无写入切换流程。

## BootROM 的官方流程

Rockchip 官方 [RK3288 页面](https://opensource.rock-chips.com/wiki_RK3288) 链接的
[RK3288 TRM V1.2 Part1](https://opensource.rock-chips.com/images/8/8f/Rockchip_RK3288_TRM_V1.2_Part1-20170321.pdf)，
第 15 页（PDF 页码与印刷页码相同）Fig. 1-2 `RK3288 boot procedure flow` 给出：

```text
external NAND → eMMC → SPI NOR → SPI NAND → SDMMC card → USB
```

图中每一级读取 `ID BLOCK` 并判断 `ID BLOCK correct?`；有效时初始化 DDR、
加载并执行该介质的启动代码，检查失败才转向下一介质。因此，只要 eMMC 的
ID BLOCK 被 ROM 接受，就不会继续从 TF 读取本项目的 IDB loader。之后是否
转而加载 TF 上的文件，取决于已经执行的 eMMC 加载器。

第 13–14 页 §1.2 `System Boot` 另列出支持的启动介质及 USB OTG 下载功能。
这里的优先级依据是 RK3288 专用流程图，不是其他 Rockchip 芯片或板卡的说明。
核查使用的 PDF 大小为 5,305,038 字节，SHA-256 为：

```text
e22d6885ad25000fc9dc62404c968ba3c8876f320fac0649a3d6154af0e25bd5
```

源码包只保存引用及核查记录，不收录整本 TRM。

## TF 加载器位置与优先级是两个条件

官方 [Boot option](https://opensource.rock-chips.com/wiki_Boot_option) 的启动阶段
表将 `idbloader.img` 放在 `0x40` 扇区，并写明
`Flash the idbloader.img to offset 0x40`。按 512 字节扇区计算，这是 32 KiB。
同页 `Boot from SD/TF Card` 的示例也使用 `seek=64`。

这个偏移用于让 ROM 找到 SD 的 ID BLOCK，不会改变 ROM 的介质检查顺序。
本项目 U-Boot 中的 TF 启动配置，只有在 ROM 或上一级加载器已经将执行权交给
本项目加载器后才会生效。同样，Android 设备树禁用 eMMC 是内核阶段的配置，
不能改变更早的 BootROM 选择。

## Recovery、Maskrom 和 USB 下载

官方 [Rockusb](https://opensource.rock-chips.com/wiki_Rockusb) 的
`Miniloader Rockusb mode`、`U-Boot Rockusb mode` 都把上电按
`recovery` / `volumn +` 列为进入 USB 下载模式的方法。这不是强制选择 TF 的
说明，也不能作为当前原版板按键行为已经验证的记录。

同页的 `Maskrom mode` 说明 `db` 会初始化 DRAM 并运行 USB plug loader。
官方 [Rkdeveloptool](https://opensource.rock-chips.com/wiki_Rkdeveloptool) 的
`Support commands`、`Flash image to target emmc` 区分了：

| 命令类别 | 文档中的作用 |
| --- | --- |
| `DB` / `db` | 下载并执行启动加载器，进入 DRAM 已初始化的 USB 下载环境 |
| `UL` / `ul` | 更新 IDB loader，写入存储；该页专门区分了 rkdeveloptool 与 upgrade_tool 的 `ul` 语义 |
| `WL` / `wl` | 写入存储扇区 |
| `GPT` / `gpt` | 写分区表 |
| `EF` / `ef` | 擦除 Flash |

`db` 本身不等于从本项目 TF 镜像启动 Android。要把 USB RAM 加载作为无写入
切换方案，还需核对具体 loader、后续执行路径及原版板进入方式，并取得实际
验证结果；当前不提供此类操作命令。通用文档中的短接方法也没有确定本用户板卡
修订版的具体位置，不能据此给出短接步骤。

## 当前可执行的首启检查

1. 完整镜像生成并通过离线校验后，把整盘镜像写入 TF 卡，完成写后校验。
2. 完全断电后插卡，先接 HDMI、打开显示器，再接电源做一次冷启动。
3. 记录画面变化、经过时间及电脑 USB 识别结果。若进入 Android，再按
   [首启指南](first-boot.md) 获取日志。
4. 若进入旧系统，保存旧系统名称、版本、能取得的启动日志及 bootloader 版本；
   不清除已有日志。随后确认既有加载器是否支持从 TF 加载本项目。

冷启动用于排除热重启状态，不会改变 ROM 的优先级。已通过写后校验的 TF 卡
不应仅因进入旧系统而反复重写；按 Recovery 也不是强制 SD 的方法。不要为了
这次检查刷写或擦除 eMMC。用户当前没有 USB 转 TTL，早期日志入口仍需后续确认。

原始证据索引、短引文及核查边界见
`records/boot-selection-source-audit.json`（本地历史证据：`records/boot-selection-source-audit.json`，未随源码发布）。
