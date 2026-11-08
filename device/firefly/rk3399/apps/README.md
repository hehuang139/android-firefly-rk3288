# 可选应用

公开源码不包含第三方 APK。RK3399 桌面默认的 YouTube 入口只选择官方
`com.google.android.youtube.tv`，不回退到 SmartTube 或手机 YouTube。

如需在私有 `userdebug` / `eng` 镜像中加入官方应用，使用
`scripts/import-youtube-tv.py` 校验原始 APK 并生成独立的 `youtube-official/`
目录，再由构建者加入私有产品树。该目录已被 Git 忽略；目录不存在时，
`preloads.mk` 不加入 APK，也不加入首次开机安装服务。

原始 APK 作为只读产品数据保存，由 `youtube-preinstall/` 中的一次性服务
在开机完成后交给 Android PackageInstaller 安装。已有同包名应用不会被
替换，用户以后卸载也不会被自动装回。详细设计、验证证据与尚未完成的
设备验收见 [官方 YouTube 集成说明](../../../../docs/rk3399-official-youtube.md)。

其他应用应单独核对来源、包名、签名、ABI 和授权条件。不要把 APK、账户、
密钥或私有节目源提交到公开仓库。

原系统的 CMFA、Kodi、云视听小电视、银河奇异果、酷喵和 BV 可以通过
`scripts/stage-rk3399-legacy-apps.py` 从已经验证的私有输入生成
`legacy-private/`。生成器保留 APK 签名字节、来源记录、开源组件对应源码和
许可文件，为 RK3399 使用独立模块名，并重新提取 ARM32 / ARM64 原生库。
SmartTube 不在这个列表内。详见 [既有应用迁移说明](../../../../docs/rk3399-legacy-apps.md)。
