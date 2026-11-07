# Firefly RK3288 Android TV port

原版 Firefly-RK3288 的 Android 17 / API 37、ARM32 电视系统源码，基于
Linux 6.18.60、Mesa Panfrost、V4L2 Request、FFmpeg 和 Codec2。
这是开发用途的 userdebug 移植，不是厂商认证产品或通用 RK3288 盒子固件。

本分支 `fix/live-channel-audio` 包含直播内置播放、AC-3/MP2 Codec2 软件解码、
地区与类型选台界面，以及受原分辨率限制的 AVC Level 元数据兼容修正。
对应组件和私有完整播放器已在板上更新并做有限实播；公开无台源 APK 单独构建，
未将它当成板上安装版本。分阶段结果见 [直播候选说明](docs/live-channel-audio-candidate.md)
与 [福建频道专项复盘](docs/福建频道专项复盘.md)。下述 `main` 的既有实测边界保留。

原始 200 台均已有逐项测试记录，另补入 7 台福建频道；筛选后的默认列表为
167 台，35 台待复核、5 台明确停用。全国短测、福建持续实播及午夜停播检验图
分别记载，详见 [逐台验证表](docs/全国频道逐项验证-20261108.md)。
筛选表已更新到板上，安装后的福建新闻又连续实播 61.81 秒；散列和验证范围见
[默认列表部署记录](docs/validation/live-channel-default-list-20261108.json)。

已在原版板卡上验证系统启动、eMMC、HDMI 桌面、H.264 硬件解码及 3.5 mm
模拟音频。H.264 的 12 秒 1080p60 样片 720/720 帧像素校验通过；本地
Surface 播放稳定窗口为 597/600 帧，中间 8 秒 480/480 帧。YouTube 实际
播放仍有轻微卡顿及 30/60 FPS 切换问题，不能把本地样片结果等同于
YouTube 60 FPS 已完全解决。HEVC 硬件节点保持关闭，VP9/AV1 硬解、4K/8K
流畅播放未验证。HDMI 音频已在 32V3H-H6A 上通过 PCM1 左右声道、Android
AudioTrack 和视频播放的实际听音；软件重启后自动连接 HDMI，192,000 帧播放进度
和只读挂载通过。视频中拔出 HDMI、等待 5 秒再插回后，画面和声音自动恢复，
且未重启；拔出期间的耳机回退、路由打开失败恢复和冷断电尚未验收。此前 DELL
P2017H 无音频能力时保持模拟输出的负例也保留。1600×900 的 NPLL 配置仅在当时测试显示器验证。

公开仓库包括完整累计内核补丁及配置、最终 DTB 对应的反编译 DTS、设备
HAL/Codec2/UI 源码、U-Boot 构建补丁、固定 AOSP manifest 和小型诊断工具。
第三方 APK、台源/签名协议、媒体资产、账号、密钥、设备日志和系统镜像不包含在内。
频道/节目单默认为空；可以加入自己有权使用的直接 URL 和独立取得的应用。

- 完整问题、证据与修复复盘：[移植复盘](docs/移植复盘.md)
- 本地镜像版本与实测边界：[固件版本与验收](docs/固件版本与验收.md)
- RAM Loader 限额修正源码：[tools/ram-loader](tools/ram-loader/README.md)
- 构建顺序与缺口：[BUILD.md](BUILD.md)
- 最终内核源与校验范围：[kernel/final/README.md](kernel/final/README.md)
- 播放链路与测试边界：[docs/playback-sources.md](docs/playback-sources.md)
- 许可与对应源码：[THIRD_PARTY.md](THIRD_PARTY.md)
- 可选媒体：[device/firefly/rk3288/tv-data/README.md](device/firefly/rk3288/tv-data/README.md)

历史板上二进制经过实测；公开无 APK/无台源版本的整个 Android 产品尚未
从干净源码重建。导出校验、语法检查和补丁回放不能替代这项验收。
目前是 SELinux permissive、无可信启动的开发配置，不应作为安全加固发行版。
