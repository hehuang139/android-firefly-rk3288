> Historical bring-up reference. For the final tested eMMC source profile and
> current validation limits use BUILD.md and docs/移植复盘.md. Old check counts
> and TF/HEVC instructions below are not current release validation.

# RK3288 HEVC backport for Linux 6.18.60

RK3288 的 H.264/VP8/MPEG-2 解码使用 `ff9a0000` 的 Hantro VPU，HEVC 使用独立的 `ff9c0000` 单元。本移植增加 `rockchip,rk3288-hevc` variant 和专用格式表，不把 RK3399 的 H.264/VP9 能力宣告给这块早期 HEVC 单元。

后端来自 Batocera 39 的 `board/batocera/rockchip/rk3288/linux_patches/linux-2000-v4l2-wip-rkvdec-hevc.patch`，保留 Jonas Karlman、Alex Bee、Nicolas Dufresne 以及源码中的 Collabora/Rockchip 归属。该补丁包含 RPS 位偏移与 I/P/B 帧参考数量修正；CABAC 和 scaling list 源自其原 MPP 适配，源码 SPDX 为 GPL-2.0。

迁移到 6.18 的改动包括：新 driver 目录、`get_image_fmt`/格式描述接口、独立 RK3288 格式表、请求控件的动态 slice 数组、Main8/NV12 范围、slice/PPS/DPB/tile 边界校验、scaling scratch 从栈移至流上下文，以及独立 HEVC 时钟、复位、IOMMU 和电源域。复位使用 Rockchip 控制器提供的 assert/deassert 接口。

`linux-6.18-rk3288-hevc.patch` 修改原 rkvdec 核心，`rkvdec-hevc.c` 是完整后端。`build-tvbox.sh` 把它们应用到独立 kernel 工作目录并生成内核和 DTB；新建工作目录可从固定的 6.18.60 tarball 重建。内核格式表上限为 4096×2304，Android C2 产品层限制 Main8 1080p 档。Main10/NV15 不在本版输出链路中。

设备树使用 0xff9c0000/0x400、SPI12、四路 HEVC 时钟、RK3288_PD_HEVC 和 hevc_mmu@ff9c0440，来源与上述 RK3288 variant 补丁一致。构建审计检查实际 ELF 符号、built-in 配置、节点地址/IRQ、Binder64 ABI 和产物 SHA-256。解码后的正确帧、音画同步、连续播放和错误流恢复以刷板播放样片验收。
