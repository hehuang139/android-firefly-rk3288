# RK3399 官方 YouTube 电视客户端集成

本说明记录 2026-11-08 为原版 Firefly-RK3399、ARM64 Android 17 准备的
官方 YouTube 集成。这里的应用是 YouTube 的 Android TV 客户端
`com.google.android.youtube.tv`，不是美国付费直播服务 YouTube TV。
当前完成了来源与签名核对、APK 离线验证、桌面选择逻辑和安装流程的主机测试。
尚未在 RK3399 上验证安装、播放、账户登录或 DRM。

## 桌面行为

桌面默认只启动 `com.google.android.youtube.tv`，优先使用该应用真正的
`LEANBACK_LAUNCHER` 入口。没有安装时显示缺少应用，不自动打开 SmartTube
或手机 YouTube。家长控制的计时分组也读取同一份包名配置。

资源 `config_youtube_packages`、`config_youtube_title` 可以被产品覆盖；
本产品的默认值是官方包名和 `YouTube`。这让产品定制有明确入口，同时避免
把第三方客户端误标成官方应用。

## 已验证的候选 APK

| 项目 | 结果 |
| --- | --- |
| 应用版本 | 5.30.304，versionCode 530304330 |
| 包名 | `com.google.android.youtube.tv` |
| 原始文件大小 | 24,487,647 字节 |
| APK SHA-256 | `65ef522869b47a033fb2dcf820cf7193a29075379ebe7094c9e5fb99ba231b34` |
| 当前签名证书 SHA-256 | `21199d112cece428c82cb0df221da24ff8674c7a982a83a17a970eec43305b4a` |
| 原生 ABI | `arm64-v8a` |
| minSdk / targetSdk | 24 / 34 |
| TV 入口 | `com.google.android.apps.youtube.tv.activity.ShellActivity` |
| 签名验证 | apksigner 验证 v2、v3 与 SourceStamp 通过 |
| ZIP / zipalign | CRC、重复条目检查及普通对齐检查通过 |
| 必需 uses-library | 无 |
| 可选 uses-library | `org.apache.http.legacy`、`androidx.window.extensions`、`androidx.window.sidecar` |

候选来自 Aptoide 的公开镜像下载，但不把镜像自己声明的“可信”当作依据。
独立信任依据是 Google 自己的 HTTPS 站点：
[youtube.com 的 Digital Asset Links](https://www.youtube.com/.well-known/assetlinks.json)
将这个确切 TV 包名映射到上述证书。再对实际 APK 运行完整签名和内容校验，
确认它与该证书一致。导入器固定这枚证书；将来换签名必须另行审查，不能通过
随意修改信任记录放行。

5.30.304 是本次取得并验证的候选，**不是最新版本声明**。检查期间镜像页面
列出了更高版本，但其下载未成功，不能把页面上的版本当成已经取得的文件。

## 为什么采用首次开机安装

该原始 APK 中的 JNI 库经过压缩。普通 PackageInstaller 能处理这种格式，
但 AOSP 的 `check_prebuilt_presigned_apk.py --preprocessed` 检查拒绝把它
直接作为已预处理的系统 APK。不能为绕过检查而解包、改 ZIP、重签名，或把
失败的检查写成通过。

因此私有产品采用以下流程：

1. 用 `prebuilt_etc` 数据模块把原始 APK 原样放进
   `/product/etc/firefly/preinstall/YouTubeTV.apk`。
2. 不使用 `PRODUCT_COPY_FILES` 复制 `.apk`；AOSP Make 明确拒绝这种写法。
3. 在 `sys.boot_completed=1` 后启动一个 `disabled`、`oneshot` 的安装服务。
4. 先确认 PackageManager 能查询包，再消耗一次安装机会；服务暂时未就绪
   时下次开机可以重新检查，尚未进行安装尝试。
5. 检查配置中的包名、版本、固定 Google 签名与 APK SHA-256。
6. 查询包含卸载保留记录在内的同名包。只要已存在，就跳过，保留原版本、
   签名与数据；不升级、不降级、不覆盖。
7. 通过 `cmd package install --user 0` 安装，单次最长 120 秒。
   不加 `-r`、`-d` 或签名绕过参数。
8. 安装后检查包名、版本、唯一 `base.apk` 路径和完整文件 SHA-256。
   安装文件与已通过 Google 签名检查的输入逐字节一致，才记录成功。

状态保存在 `/data/misc/firefly-youtube-preinstall/`。`attempted` 表示这一次
机会已经消耗，`success` 保存已安装原始 APK 的哈希，`status` 记录结果。
尝试过后不会每次开机重试，后来主动卸载也不会被强制装回。
互斥目录放在 `/dev` 的临时文件系统中，避免上次突然断电留下永久锁。

当前服务使用 `u:r:su:s0`，生成的产品配置只允许 `userdebug` / `eng`。
这是开发镜像方案，**尚未完成 `user` 发布构建和 enforcing SELinux 的兼容性
验证**。发行版本需要专用安装服务、最小权限策略和单独验收，不能直接宣称可用。

## 准备私有产品目录

公开仓库只包含导入器、运行时服务、测试和说明，不附 APK。
信任记录至少包括：

```json
{
  "package": "com.google.android.youtube.tv",
  "apk_sha256": "已取得文件的64位小写SHA256",
  "signer_sha256": "21199d112cece428c82cb0df221da24ff8674c7a982a83a17a970eec43305b4a",
  "version_code": 530304330,
  "acquisition": "mirror-with-google-assetlinks-verification",
  "signer_provenance": "说明如何独立核对Google发布的Digital Asset Links及对应包名",
  "listing_url": "https://play.google.com/store/apps/details?id=com.google.android.youtube.tv"
}
```

在有相应 AOSP 主机工具的 Linux 构建机运行：

```sh
python3 scripts/import-youtube-tv.py \
  --apk /private/input/YouTubeTV.apk \
  --trust-record /private/input/youtube-tv-trust.json \
  --aosp /path/to/aosp \
  --report /private/output/youtube-validation.json \
  --stage-dir /private/stage/device/firefly/rk3399/apps/youtube-official
```

目标目录必须是尚不存在的 `youtube-official`。工具在独立目录完成校验与暂存，
不会安装到设备，也不会下载、改写或签名 APK。生成 `Android.bp`、`preload.mk`、
`youtube-tv.conf`、`validation.json` 和保持原始字节的 `YouTubeTV.apk`。
确认报告后，构建者再把目录放进私有产品树，避免正在运行的 Soong 扫描读到
只生成了一半的文件。

默认验证目标支持 `arm64-v8a` 和 `armeabi-v7a`，与本产品 `zygote64_32`
一致。64 位操作系统并不等于所有应用都必须是 64 位；每个 APK 应按实际
ABI 和产品兼容层核对。本次官方候选确实包含 ARM64 库。

## 已完成与待验收

主机测试覆盖：15 项导入元数据和来源策略，9 项一次性安装流程，以及生产
`AppLaunch.java` 的官方包选择、资源覆盖、Leanback 优先与家长控制测试。
安装流程测试运行生产 shell，使用隔离临时目录和模拟 PackageManager；
它能验证重复安装、已有包保护、哈希不符、服务未就绪和安装失败等分支，
**不能代替 Android 真机测试**。

RK3399 连接后的验收顺序：

1. 确认产品数据文件、Google 证书和哈希，以及一次性服务状态。
2. 确认桌面打开官方 TV Activity，重启不重复安装。
3. 测试未登录播放、暂停/快进/返回和音频，记录实际视频格式、解码器与丢帧。
4. 用户需要账户功能时，再测试扫码或遥控器登录；不从“可打开”推断登录成功。
5. 根据具体内容另测 DRM、付费内容与画质；不从 ARM64 或 APK 签名推断 DRM 能力。

Google 官方说明支持 TV 访客使用方式，但这不能证明自编译 AOSP 的访客播放
或登录一定可用。GMS 不属于 AOSP，设备认证、Google 服务授权和 DRM 都是
不同事项。当前镜像也有域名过滤功能，遇到服务连接问题应依据具体请求排查，
不能简单断定是解码器、GMS 或网络其中某一项。

## 参考资料

- [官方 Play 应用页](https://play.google.com/store/apps/details?id=com.google.android.youtube.tv)
- [Google 发布的包名与签名映射](https://www.youtube.com/.well-known/assetlinks.json)
- [YouTube TV 设备登录帮助](https://support.google.com/youtube/answer/3015415?hl=en)
- [Android GMS 说明](https://www.android.com/gms/)
- [Play Protect 设备认证说明](https://support.google.com/googleplay/answer/7165974?hl=en)
- [Android 兼容性概览](https://source.android.com/docs/compatibility/overview)
- [Google Play services 概览](https://developers.google.com/android/guides/overview)
- [Widevine 概览](https://developers.google.com/widevine/drm/overview)
- [TV 应用入口要求](https://developer.android.com/training/tv/get-started/create)
