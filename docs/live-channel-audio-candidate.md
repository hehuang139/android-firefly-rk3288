# 直播内置播放、频道分组与 AC-3/MP2 更新

本页对应 `fix/live-channel-audio`，基于已验收 HDMI 修复的 `main` 提交
`6c334b856efd4d76a4ae0588974f6e6225a3216e`。最初的离线候选现已进入组件安装和
实际直播回归阶段。我分别记录公开源码构建与私有频道版本的板测：公开版本保持
空频道表，最新公开 APK 已完成构建和验签，尚未安装到板卡；实际板测使用另一个
私有播放器及私有频道配置，不能把二者视为同一产物。

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
（`audio/ac3`）和 `c2.firefly.mp2.decoder`（`audio/mpeg-L2`），两者采用 FFmpeg
软件音频解码，视频硬解另行验证。我配对导出四个
音频组件/接口源文件、组件 store 与 XML。音频输入使用带零填充的 packet，
PCM 复制检查实际字节数和映射容量，转换使用公开 swresample API。

FFmpeg 仍固定原 revision 和 Android V4L2 Request 补丁，配置仅增加 AC-3、MP2
解码器、`ac3`/`mpegaudio` parser 和 swresample。未启用 GPL/nonfree 选项。
`Android.bp` 增加 `libfirefly_swresample` 及 Codec2 服务依赖；所有版权头和
Apache/LGPL 许可保留。最初音频候选没有修改视频组件。随后我只在视频接口中
补入 AVC 4.2、5、5.1 三个 level 元数据常量，具体范围见下文；H.265 硬件节点
继续关闭。

## 频道界面和有限 AVC level 修正

我将旧的单列频道对话框改为“地区 / 类型”双页频道面板。地区分组优先使用
省份代码和元数据，类型允许一台属于多个类别；中央、省级卫视、地方台及其他
分类只影响显示，仍映射到原目录索引，保留目录本身的顺序、编号和换台目标；
省份组显示时优先列出卫视频道。
面板显示收藏、当前频道和实际节目单内容，没有合成节目名称。方向键和确认键
可浏览、播放；ESC/Back 先关闭面板，长按确认键不重复打开。鼠标或触摸的第一次
点击即可激活控件，避免只取得焦点而需要再点一次。

公开改动仅涉及五个 Java 文件：`ChannelCatalog`、`ChannelCategories`、
`ChannelPicker`、`LiveActivity`、`ScriptStringTable`。我另外导出了通用字符串
字面量数组读取器，它只读取数据，不执行 JavaScript；拒绝表达式、模板插值、
稀疏数组、注释和数组后的附加代码。输入上限为 65,536 个 UTF-16 代码单元，
最多 512 项，每项最多 8,192 个代码单元。公开 provider hook 仍保持禁用，
通用读取器没有连带导出私有频道解析器、接口地址或签名逻辑。

福建的三条真实 1080p25 官方节目在码流中声明 H.264 Level 5.1，原 C2 接口严格
列表却只接受到 Level 4.1，因而出现有声音、无画面的配置失败。我用同一份原始
TS 作对照，没有改写 SPS 或转码：仅去除传给解码组件的 level 元数据后，精确
指定的 `c2.firefly.h264.decoder` 可将三份有限样本解码至 EOS；修正接口后，
福建新闻样本保留原始元数据也输出了 99 帧并到达 EOS。

我据此仅扩充接口可接受的 AVC level 常量。`C2FFMPEGVideoDecodeInterface.cpp`
的其他代码不变，图片尺寸仍限制在 96×96 至 1920×1088，codec XML、码率与
宏块资源约束保持原样。这证明本轮受原资源限制的样本可以进入并通过指定组件，
不表示 RK3288 支持所有 Level 5.1 码流，也没有增加 4K/8K 或 H.265 硬解能力。
源文件范围和本次验证见
[UI 与 AVC level 记录](validation/live-ui-avc-level-20261108.json)。

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

最初公开可选内容版本的 24 个 Java 源文件构建记录仍保留在历史验收 JSON 中。
加入这次通用 UI 源文件后，最新公开版本为 27 个 Java 源文件，已从实际公开
Manifest、资源及源码完成 AIDL、javac、dex、资源编译链接、对齐、签名和验签，
10 个构建阶段均通过。APK SHA-256 为
`177ba387a37597dd7d4c09d85eaf1c6fbcf92645e8c873521d6d4ffacca4fb02`，
大小为 82,469 字节，V3 签名验证通过。本轮重新核对的 33 项构建输入与当前
公开文件逐项散列一致。这个 APK 没有加入仓库，也没有安装到开发板。

我还用实际公开 `ScriptStringTable` 源码完成了 23 项 JVM 边界测试，覆盖有效
转义和多行字符串、输入/项数/单项长度的边界，以及代码、插值、稀疏数组和
错误转义的拒绝。17 个原播放方法及目录源解析、请求头传递逐字节保留，
`play()` 只增加当前频道的界面标记；没有把私有刷新器带入公开版本。
构建输入及源码来源见
[本轮 provenance](provenance/live-ui-avc-level-20261108.json)。

最初音频候选的 Codec2 与四个 FFmpeg 库已通过配对 ARM32 编译/链接和 ELF 检查：
没有 RPATH、可执行栈，原 avcodec/avutil/swscale 导出符号全部保留。当时组件服务 SHA-256 为
`6c11fc03fa8df2c1cc0c5f7326f7e8bad18879d63b4b6a7088da170712a4b7e3`。
这组最初音频候选的来源和准确源文件散列见
[历史候选 provenance](provenance/live-channel-audio-candidate.json)，
完整脱敏组件结果见 [历史候选验收记录](validation/live-channel-audio-candidate.json)。
公开导出仅去掉音频组件末尾一处行末空格，编译输入与公开源码的两个散列分别保留。
最初音频候选的散列对应、当时视频源不变、历史基线保留、私密信息和链接检查见
[候选源码复查](validation/live-channel-audio-source-review.json)。

在单独安装的私有播放器和修订 C2 组件上，福建专项已记录十台约 61–65 秒的
连续实播：七台为真实高清节目，两台泉州为 360p，厦门卫视为 576p。测试同时
核对实际出帧、解码组件、运行中的 AudioTrack 和解码画面；厦门卫视实际使用
`c2.firefly.mp2.decoder`。有些采样区间零新增丢帧，但开台时仍有初始丢帧，
不能表述为全程零丢帧。AudioTrack 在运行也不能替代逐台扬声器听音。

这些正常节目实播结果来自私有 `826e` 播放器及当时的频道配置，说明相应组件和
线路在该观察窗口内可持续工作，不是公开空目录 APK 的板测。后续私有 `0528`
动态版本曾在跨日后无法解析石狮，原始失败记录继续保留。改用官方当前直播入口
后，已安装的私有 `1386` 版本完成石狮 64.61 秒、晋江 64.80 秒的午夜连接和解码
检查，分别有 1618 帧 / 新增丢 8 帧、1620 帧 / 新增丢 0 帧，均保持一个活动连接。
两台截图都是带台标的停播检验图，因此这轮通过只覆盖当前入口与解码，不算新增
正常节目，也不是对十台频道在新 APK 上的完整复测。两小时票据到期续播、逐台
听音、长时稳定性及新整盘镜像仍未完成。只有石狮另有官方媒体近静音的测量，
晋江没有同样的测量；运行中的 AudioTrack 不能代替听音。
我把版权提示片、检验图、真实节目、短时硬件样本和连续板测分开记录，过程及
各轮验证版本见独立的 [福建频道专项复盘](福建频道专项复盘.md) 和
[脱敏验证记录](fujian-channel-validation.json)。

这些更新尚未组成新的已验收整盘镜像，不能将它们命名为已完成验证的新固件。
`docs/validation/final-public-review.json`、`public-profile.json` 和 HDMI 记录
继续保存 `main` 阶段的历史验证；当前候选结果单独记录。
