# 直播内置播放与 AC-3/MP2 候选

本页对应 `fix/live-channel-audio`，基于已验收 HDMI 修复的 `main` 提交
`6c334b856efd4d76a4ae0588974f6e6225a3216e`。这是离线候选，尚未安装到板卡；
已有 H.264、耳机与 HDMI 听音结果属于原基线，不能替代候选回归。

## 问题与修改范围

历史频道表共有 193 个频道、261 条线路，其中 239 条使用内置播放、22 条指定
Kodi。这 22 条的历史音轨标注是 18 条只有 AC-3、3 条同时含 AAC/AC-3、1 条 MP2。
旧选择器把 AAC/MP3 交给内置播放器，其余转交 Kodi；直播页又执行台源中的
`player` 提示，因此部分频道会直接离开电视界面。这些计数来自历史配置，
不表示线路现在可达，也不是对所有频道的实际播放验收。随后核对实际打包配置，
它包含 200 个频道、268 条线路；193/261 是较早的历史叠加表，不是当前清单。
针对实际打包的 268 条线路，新一轮网络复查取得了有限实际媒体片段，结果如下。

| 本次构建主机网络结果 | 频道数 | 线路数 |
|---|---:|---:|
| 直接连接取得媒体 | 110 | 123 |
| 仅经现有代理取得媒体 | 39 | 44 |
| 本次未确认 | 51 | 101 |
| 总计 | 200 | 268 |

合计 149 个频道至少有一条成功线路，167 条线路取得媒体。101 条未确认线路按
最后一次尝试互斥分类为 HTTP 5xx 69、解析器失败 11、HTTP 404 8、请求/清单失败 7、
非 HLS 5、超时 1；它们的 202 次失败尝试另计，不能当成 202 条线路，也不表示永久失效。

检查时间为北京时间 2026-11-07 09:22:37–09:24:18。构建主机以 6 并发、
每请求 10 秒上限取得 HLS 和第一实际媒体片段，再用 ffprobe 读取流信息；
没有做整段帧解码或板上播放。167 条成功线路均识别到 H.264，音轨按线路统计为
AAC 150、AC-3 19、MP2 1，多音轨线路会重叠。编码名称落在候选范围内，
仍不证明所有 profile、分辨率、实时性或音画同步已通过。
脱敏统计和采样范围见 [线路网络复查](validation/live-channel-availability-20261107.json)。

候选忽略历史 `player` 提示，移除自动外跳 Kodi 的入口和委派播放状态，所有
直播线路都留在同一 `LiveActivity`。原 `MediaPlayer.setDataSource` 的请求头
传递、换台、换线路和返回逻辑保留；应用页里主动启动 Kodi 的入口仍在。

播放器留在内部还需要补齐音频能力。候选添加 `c2.firefly.ac3.decoder`
（`audio/ac3`）和 `c2.firefly.mp2.decoder`（`audio/mpeg-L2`），配对导出四个
音频组件/接口源文件、组件 store 与 XML。音频输入使用带零填充的 packet，
PCM 复制检查实际字节数和映射容量，转换使用公开 swresample API。

FFmpeg 仍固定原 revision 和 Android V4L2 Request 补丁，配置仅增加 AC-3、MP2
解码器、`ac3`/`mpegaudio` parser 和 swresample。未启用 GPL/nonfree 选项。
`Android.bp` 增加 `libfirefly_swresample` 及 Codec2 服务依赖；所有版权头和
Apache/LGPL 许可保留。视频组件及硬件加速源码逐字节未变，H.265 硬件节点继续关闭。

## 源码构建

先完成根目录 [BUILD.md](../BUILD.md) 的固定 AOSP、工具链、NDK sysroot 和
CRT 准备。`PORT_ROOT`、`FIREFLY_WORK_ROOT` 沿用该文档定义，在独立目录构建：

```bash
cd "$PORT_ROOT"
python3 device/firefly/rk3288/media/build-ffmpeg.py \
  --aosp "$FIREFLY_WORK_ROOT/aosp" \
  --work "$FIREFLY_WORK_ROOT/ffmpeg-live-audio-candidate"
```

脚本生成 avcodec、avutil、swscale、swresample 四个共享库，并安装对应 headers，
包括 `include/libswresample/`。仓库不附这些二进制。禁止用历史三库混配新 Codec2
服务；组件构建和离线 ELF 审计针对同一组配对库。

将本分支源文件复制到 AOSP 的标准安装方式为：

```bash
bash "$PORT_ROOT/build.sh" install
cd "$FIREFLY_WORK_ROOT/aosp"
source build/envsetup.sh
lunch aosp_firefly_rk3288-aosp_current-userdebug
m android.hardware.media.c2-service-firefly FireflyTV
```

上面是产品集成的构建入口。已有验证使用隔离的 AOSP ARM32 编译/链接环境；
本分支尚未重新完成整个干净 Soong 产品图和 Android 整盘构建。
仅构建公开可选内容版本的电视 APK 时，也可使用已提供的工具：

```bash
python3 "$PORT_ROOT/scripts/build-tv-apk.py" \
  --aosp "$FIREFLY_WORK_ROOT/aosp" \
  --output "$FIREFLY_WORK_ROOT/live-audio-candidate/FireflyTV-public.apk" \
  --report "$FIREFLY_WORK_ROOT/live-audio-candidate/launcher-build.json"
```

这个流程从调用方 AOSP 使用平台签名材料，源码包不包含私钥。公开频道表仍为空，
没有导出历史私有台源、解析协议、token、真实频道 URL 或完整设备日志。

## 已完成和待验证

公开可选内容版本的 24 个 Java 源文件已完成独立编译、dex、资源打包和签名，
manifest 与资源不变；APK SHA-256 为
`e0e03b7961b71a9551d4bbc94349d7d92355dbb30780f77e132635c5909528ca`。
这个散列只用于追溯构建，没有将 APK 放入仓库，也没有把另一份私有完整台源
版本的构建结果当成公开版本的证明。

Codec2 与四个 FFmpeg 库已通过配对 ARM32 编译/链接和 ELF 检查：没有 RPATH、
可执行栈，原 avcodec/avutil/swscale 导出符号全部保留。组件服务 SHA-256 为
`6c11fc03fa8df2c1cc0c5f7326f7e8bad18879d63b4b6a7088da170712a4b7e3`。
来源和准确源文件散列见 [候选 provenance](provenance/live-channel-audio-candidate.json)，
完整脱敏组件结果见 [候选验收记录](validation/live-channel-audio-candidate.json)。
公开导出仅去掉音频组件末尾一处行末空格，编译输入与公开源码的两个散列分别保留。
公开源码的散列对应、视频源不变、历史基线保留、私密信息和链接检查见
[候选源码复查](validation/live-channel-audio-source-review.json)。

尚未完成板上 codec 枚举、AC-3/MP2 本地解码至 EOS 与 PCM 对照、普通 H.264
回归、板上网络直播、换台和返回体验、候选持久安装/重启。本次线路复查从构建
主机取得媒体并通过 ffprobe 识别，也不能替代这些板上测试。

候选未加入已验收的 fix2 镜像，不能将其命名为已完成硬件修复的新固件。
`docs/validation/final-public-review.json`、`public-profile.json` 和 HDMI 记录
继续保存 `main` 阶段的历史验证；当前候选结果单独记录。
