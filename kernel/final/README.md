# 最终 RK3288 内核对应源码

本目录只适用于历史 RK3288 ARM32 产品。RK3399 的独立内核入口见
[kernel/rk3399](../rk3399/README.md)，不沿用这里的累积补丁或 ARM32 BPF 修正。

本目录给出已测试内核对应的完整累积源码差异、最终配置和最终设备树，基线为未经修改的 Linux 6.18.60。它不只是最后一轮 DMA 地址修复。上游源码、累积补丁和本目录配置组合起来可以还原对应源文件；没有修改原始服务器源码树。

## 输入与已测试工件

| 项目 | SHA-256 |
| --- | --- |
| 官方 `linux-6.18.60.tar.xz` | `3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e` |
| 已测试 `zImage`，12,227,072 字节 | `8c044786118434fc737d9c17b32bdbe4206fcd4112b625d30f29a4ba3124317a` |
| 最终 `.config` | `96f53bfe2007da3beabcec566e16cdc3425cc065c4f043316a67b1482b5498eb` |
| 最终 DTB，43,752 字节 | `2021fedaf9241b18d8184191c24a740f05beaceac0aeffb80c41376e1c815c5b` |

上游来源：<https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.18.60.tar.xz>。已保留的上游审计记录确认归档散列和 Greg Kroah-Hartman 的发布签名；导出时再次核对归档散列。公开签名指纹为 `647F28654894E3BD457199BE38DBBDC86092693E`。

`changed-files.json` 列出相对该归档的全部新增、修改或删除文件及哈希；`kernel-source-validation.json` 记录完整比对和补丁重放结果。`source-overlay/` 是便于审阅的最终变更文件副本；完整源码还包括上游归档中未改变的文件。`source-tree-manifest.json` 给出对应完整源树的逐文件散列。两份 Kconfig 临时合并文件不是构建源码，已排除并在验证记录中注明。

## 构建

需要 Linux、GNU make、Git、tar/xz、Python 3、ARM hard-float 交叉编译工具链和 DTC，以及 Linux 内核常规构建依赖。原测试构建使用 `arm-linux-gnueabihf-gcc 11.4.0`；DTB 回编译校验使用 DTC `1.7.2-g52f07dcc`。

先取得上述散列匹配的上游归档，再执行：

```sh
sh build-kernel.sh ./linux-6.18.60.tar.xz ./new-kernel-build 8
```

脚本拒绝复用已有输出目录，在独立目录解包、检查和应用完整补丁，使用最终配置构建 `zImage`，然后从单独的最终 DTS 生成 DTB。脚本不写任何板卡，也不修改调用者已有的 Linux 源树。

导出审计重放了全部源码差异，但没有重新进行一次完整 clean kernel build。上表内核散列来自已实际构建和实板验收的工件；不同编译器、DTC 或环境可能改变二进制，不能仅凭脚本准备完成就宣称任意环境 bit-for-bit 可复现。构建元数据在脚本中固定为原测试值，输出散列供进一步核对。

## 最终设备树的来源

`device-tree/rk3288-firefly-es8323-npll216.decompiled.dts` 是最终 DTB 的完整反编译文本，**不是原始手写 DTS**。它包含当时已验证的 ES8323/耳机引脚、电源轨、定制 HEVC 禁用和 NPLL 216 MHz 配置。该文本用上述 DTC 回编译后，43,752 字节与最终 DTB 逐字节相同。

因为标签被数值 phandle 取代，回编译出现 254 行静态 binding/phandle 警告，输出仍完全一致；这不是 DeviceTree schema 验证通过的声明。具体记录见 `device-tree/verification.json`。

累积源码补丁中保留的板级 DTS 是历史源树的一部分。要得到最后发布 boot 中的 DTB，应使用本节明确指定的完整反编译 DTS；不能将普通 `make dtbs` 生成的旧板级变体误认为最后工件。

## 保留的诊断代码与当前限制

对应最终已测试构建的源码保留了启动排障过程中加入的 initcall、通用电源域、PMU/HEVC/IOMMU、UART 和每 CPU 诊断代码，以及 Hantro 接受合法 DMA 地址 0 时的一次性日志。这些内容不能伪装成全部都已证明必要的功能修复，也不能在没有重新构建、回归和更新工件散列的情况下静默删除。`changed-files.json` 和完整补丁是准确范围。

当前恢复启动的方法禁用了定制 HEVC decoder 及其 MMU；四路时钟等中间候选曾单独失败，保留相关源码不等于 HEVC 已经修好。Hantro 的 H.264 路径保留。最终 H.264 DMA 缺失参考帧判据使用 `DMA_MAPPING_ERROR`，允许合法的 DMA 地址 0，并保留后处理缓冲分配失败处理。

内核还包含该 ARM32 userdebug 移植需要的 BPF 配置、网络功能和模拟音频驱动配置。Android 的 NetBpfLoad、HAL、gralloc、init rc、应用和系统分区修改另有源码导出，本目录单独不能组成完整 Android 系统。

Linux 源码沿用各文件 SPDX 标识和上游 `COPYING`/`LICENSES` 条款；本项目的移植不改变原文件许可。公开整套项目时应同时提供上游版本、完整累积补丁、配置、设备树和构建说明，不能只附最后七个 Hantro 文件。
