> 历史 bring-up 资料。当前构建与验收范围以 [BUILD.md](../BUILD.md) 和独立移植复盘为准。旧 alpha、TF、HEVC 与旧校验项不代表当前发布已验证状态；当前 HEVC 硬件节点停用，最终板上验收介质为 eMMC。

# 儿童益智与家长模式

电视首页 → 儿童益智 → 家长设置。首次使用建立 4–8 位数字 PIN，没有出厂默认密码。
默认题目适合 3–5 岁：颜色匹配、形状匹配、1–5 数数，每轮各一题；方向键选择、确定键作答，
答错可以重试，没有答题倒计时。可选更简单的 1–3 数数。小游戏离线运行，无账号、广告或上传。

默认每段观看 15 分钟、每日累计 60 分钟、答完三题续看 5 分钟，均可在家长设置中调整。
按儿童视频应用的前台使用时间计时，包括应用内选择节目的时间。
到时停止外部视频应用，内置视频通过离开播放页释放播放器，然后显示益智题。
答题通过后返回儿童专区，可重新打开视频；外部应用的播放位置由其历史记录功能恢复。
每日上限不能通过答题增加；达到上限后仍可玩益智游戏，继续看视频需要家长退出家长模式。

内置认识颜色、数一数两段原创无配音短片，各 40 秒；家长可陪同读出颜色和数量。
另提供银河奇异果、酷喵、Kodi 儿童视频入口，初始均未授权。
家长须先在各视频应用内启用儿童模式/分龄，或为 Kodi 准备儿童文件夹，再选中允许。
入口打开对应应用主页，不替代提供方的内容过滤；电视应用内会员及地区条件按提供方规则。
儿童首页不显示 B 站、BV、SmartTube、代理工具或全部应用列表。

计时和模式状态存储在设备保护区的私有 SharedPreferences；每次使用前预记最多 5 秒，
重启和应用切换不会清零。退出儿童视频应用会停止其后台播放；锁屏时也停止外部应用。
日期只向前推进，回拨时钟不会刷新用时。家长模式在开机广播和主页启动时恢复监控。
家长 PIN 使用独立随机盐和 PBKDF2-HMAC-SHA256，连续五次错误后需等待 30 秒。
家长设置退出到后台后关闭，重新打开需再次验证 PIN。

源码位于 tv/src/org/firefly/tv/ 的 KidsActivity、ParentalActivity、ParentalPrefs、
WatchTimeTracker、PuzzleActivity、PuzzleRound 和 WatchBudget。
WatchTimeTracker 使用本固件平台签名和系统 UID 权限读取前台任务、停止已授权视频应用，
其 service 和所有家长/益智 Activity 均不向其他应用导出。
此设计面向家庭遥控器使用；USB 调试、重新刷机和修改系统分区不属于家长 PIN 的管控入口。

验证入口：

```bash
python3 tvbox-port/scripts/test-parental.py \
  --jdk aosp/prebuilts/jdk/jdk21/linux-x86 \
  --report tvbox-port/records/parental-host-tests.json
wc-java-lint check tvbox-port/device/firefly/rk3288/tv \
  --only checkstyle,pmd,simian,lizard --format json -o tvbox-work/java-lint-parental.json
```

主机测试执行实际计时、PIN 和出题代码，SharedPreferences 使用测试替身。
板上验收应检查：两段内置视频播放、遥控答题、第三方应用到时音画停止、每日上限、
重启保留用时、切换应用/主页键限制、家长 PIN 和冷却，以及 HDMI 音量/返回键。
