# 网络与分辨率设置修复

我在实机检查中发现：以太网已经联网，但“网络和互联网”只显示其他选项；显示器提供了 22 个有效模式，“分辨率”页面却是空白。两项问题都在 AOSP TvSettings 的入口判断中。

`ConnectivityListener` 原来只在 `WifiManager` 存在时注册整个网络生命周期监听。在最初尚未接入无线服务的阶段，以太网监听也没有注册，设置界面一直认为没有可用接口。第一份补丁把通用监听移到无线条件之外；它不修改 IP、DNS、代理或无线功能声明。

`ResolutionSelectionFragment` 原来在系统没有提供开机首选显示模式时立即退出，连已经枚举出来的支持模式也不显示。第二份补丁使用默认模式作为界面回退值，继续生成模式列表，并正常监听显示变化。“自动”仍通过系统清除用户首选模式；缺少真实首选模式时不显示一个推测的自动分辨率。确认框保留切换前实际模式，原有倒计时恢复流程仍在。

接入无线功能后，我又发现 `NetworkFragment` 只要看到当前默认网络是以太网，就隐藏无线网络列表、添加网络和快捷连接，并提示必须拔网线。这些条件直接写在 Java 中，当前版本没有对应的资源覆盖开关。第三份补丁让无线功能开关独立控制这些入口，取消有线连接时清空无线列表和要求拔线的提示；有线状态、IP 和代理入口继续保留。它不改变 Android 的路由优先级，也不主动连接任何无线网络。

补丁位于 `patches/tvsettings/`，对应 AOSP `packages/apps/TvSettings` 提交 `d726afd01e0189180f2e4c61b6c47c556db372da`。`scripts/install-port.py` 在 `bash build.sh install` 时自动应用，校验原文件与最终文件 SHA-256，支持重复执行；遇到其他版本或无关文件改动会停止。

在按 [BUILD.md](../BUILD.md) 准备好的构建环境中，执行完整构建即可包含修复。只重编设置应用可使用：

```bash
bash build.sh install
cd "$FIREFLY_WORK_ROOT/aosp"
source build/envsetup.sh
lunch aosp_firefly_rk3288-aosp_current-userdebug
m TvSettings
```

应用输出为 `$ANDROID_PRODUCT_OUT/system_ext/priv-app/TvSettings/TvSettings.apk`。这些命令只构建，不安装或烧录。只重编 FireflyTV 桌面 APK 不会包含 TvSettings 修复。

三份补丁已经一起隔离编译，最终 APK SHA-256 为 `0db3ed09ee7c487fe2b857d952f96cc5519acf861df5898e358e43cc5ad890f0`。Manifest、请求权限及全部非 DEX 资源与原板包逐字节一致，平台签名、内容摘要和 zipalign 检查通过。三份补丁的重放测试均检查首次应用、重复应用、错误提交，以及每个补丁文件的无关改动拒绝。

最终 APK 已安装到原版开发板。插着网线时，真实无线网络列表可见；选择安全热点可进入掩码密码输入页，取消后回到网络页；添加网络的名称编辑页、快速连接二维码页也能打开并取消。通过页面关闭再开启 WLAN，真实列表恢复，有线链路全程保持连接。测试未输入任何热点密码，未尝试无线认证、获取 IP 或手机扫码配网。

前一版已经实际验证有线静态 IP、手动代理的编辑与取消，以及分辨率列表。输入向导需要依次退出键盘/编辑状态和页面，不能把第一下 Back 仍停在编辑页判成死锁。测试没有保存新的 IP、代理或显示模式，这些配置生效与恢复仍需单独验收。无线底层的来源、一次受限 SDIO 恢复和冷启动边界见 [Wi-Fi 接入记录](wifi-bringup.md)。本轮实机 UI 结果见 [网络设置验收](validation/network-ui-v3-20261108.json)。

可在已同步的 AOSP 树上复跑补丁安装测试；它只使用临时 Git 副本，保留原工作树：

```bash
python3 scripts/test-tvsettings-patches.py "$FIREFLY_WORK_ROOT/aosp" --report /tmp/tvsettings-patches.json
```

本次结果保存在 [补丁验证记录](validation/tvsettings-patches.json)。
