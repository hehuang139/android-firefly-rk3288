# Firefly-RK3288 电视遥控

默认输入路径为原板 GPIO7_A0 红外接收器和 USB HID 遥控器。原厂 12 键遥控表内建在内核，Android 按设备名 `gpio_ir_recv` 加载专用布局；第三方 NEC、RC5、RC6、Sony 遥控可从电视设置学习。原板电源键 GPIO0_A5 由原 DTS 保留。

原厂命令码来自 [Firefly 官方 12 键遥控图](https://github.com/Firefly-docs/products-docs/blob/0d90ce26a859bda4912898d6ccf66d90b0869c56/rk3288_img/module_ir_remote_info.png)，协议 NEC，线上的用户码 `00FF`，主线解码地址为 `00`。旧 PWM 文档中的 `eb/ec/fc/...` 是命令反码，不能直接拿来作为 rc-core scancode。这里使用实际命令 `14/13/03/...`。

| 按键 | NEC scancode | Linux keycode |
| --- | --- | --- |
| 电源 | `0x14` | 116 |
| 菜单 | `0x13` | 139 |
| 上/下/左/右 | `0x03/02/0e/1a` | 103/108/105/106 |
| 确认 | `0x07` | 352 |
| 设置 | `0x5c` | 141 |
| 主页/返回 | `0x48/01` | 102/158 |
| 音量减/加 | `0x58/0b` | 114/115 |

`POWER` 交给 Android 电源管理处理待机和唤醒；IR DTS 的 `wakeup-source` 允许请求 GPIO 唤醒。刷板验证时应分别检查正常按键、按住重复、待机后唤醒。完全断电时接收器、GPIO 和 Linux 均未运行，断电后上电属于供电/PMIC/引导固件设计。

## 学习接口

`firefly-remote` 由 init 启动，以 VINTF stable AIDL v1 服务 `vendor.firefly.hardware.remote.IRemote/default` 提供控制。接口为 `String request(String json)`，客户端链接 `vendor.firefly.hardware.remote-V1-java`，服务端链接 `vendor.firefly.hardware.remote-V1-ndk`。接口冻结快照、SHA-1 API hash 保存在 `aidl/aidl_api/vendor.firefly.hardware.remote/1/`。

服务在每次 Binder 请求开始时核对调用者 UID 为 0 或 1000，再解析最长 4096 字节的 JSON；返回一个 JSON 字符串。Binder 请求按互斥锁串行执行，防止学习期间另一个客户端同时修改键表。系统签名共享 UID 1000 的电视设置可以调用，userdebug/eng 中的 adb root 和 su 可排查。普通应用与 UID 2000 的 adb shell 请求被拒绝。

```json
{"command":"status"}
{"command":"capture","timeout":15}
{"command":"set","scancode":20,"keycode":116}
{"command":"reset"}
{"command":"cec","enabled":true}
```

`capture.timeout` 为 1–20 秒，默认 15。成功返回 `{"ok":true,"scancode":20,"protocol":"nec"}`；等待期间只独占板载红外输入，避免电源/主页键退出向导，USB 输入仍可操作。`set` 接受 uint32 scancode 和 Linux keycode，保存到 `/data/vendor/firefly/ir-keymap.json`，重启后自动恢复。`reset` 恢复 `/vendor/etc/firefly/ir-defaults.json` 中的官方遥控表。

错误返回 `{"ok":false,"error":"timeout"}` 等，其中 `ir_unavailable` 表示接收器/LIRC/input 设备尚未就绪，`persist_failed` 表示持久化失败且尝试回滚当前表。新映射由 `EVIOCSKEYCODE_V2` 安装到内核，文件采用临时文件、fsync 和原子 rename。

`cec` 接受布尔 `enabled`，由 vendor 遥控服务写入受限属性，init 按属性启停 CEC 输入服务；该命令不依赖红外接收器存在。`status` 和 `cec` 返回的 `cec_enabled` 表示持久化开关，`cec_available` 表示 `/dev/cec0` 可打开且支持逻辑地址、发送和 rc-core 按键能力；它不表示 PCB 引脚或电视端已经连通。CEC 地址分配与连接变化写入 `firefly-cec-input` 日志。`status.available` 单独表示板载红外输入/LIRC 是否就绪，不能用请求成功代替接收器就绪。

关闭 CEC 时，服务等待 init 确认输入进程已停止，再清除属于 `Firefly TV` 的 playback 逻辑地址，从而停止内核 RC 输入。Linux 的 CEC 配置保存在适配器中，单纯关闭文件或结束进程不会清除它。输入进程也处理 SIGTERM/SIGINT 并尝试清理，init 配置使用 `gentle_kill`；Binder 关闭路径负责补做超出 init 200 毫秒退出窗口的清理。其他应用拥有的 CEC 配置会保留，停止超时或清理失败分别返回 `cec_stop_timeout`、`cec_cleanup_failed`。

## HDMI CEC 可选输入

`firefly-cec-input` 实现 Linux CEC playback 地址和 rc-core 按键路径；它不使用 AOSP 的 Mock CEC HAL。内核已编入 DW-HDMI CEC 和 MEDIA_CEC_RC，`dw_hdmi.kl` 提供 Android 布局。原版 PCB 的 CEC 引脚走线还需对原理图确认，因此此服务默认禁用。确认 HDMI pin13 接 GPIO7_C0 后可把 `kernel/cec-c0-optional.dtsi` 包含进 DTS，重编刷入，再调用 `{"command":"cec","enabled":true}`。GPIO7_C7 与 UART2 调试串口共用，不能随意切换。

CEC 输入范围为导航、播放、音量等按键；电视也需开启对应 HDMI 口的 CEC。完整 Android HDMI 控制、ARC/eARC 和设备认证不由该输入服务提供。

构建验证包括 Linux 6.18.60 的 ARM 交叉编译、内核配置/符号/两种启动介质设备树核对、Android keylayout 名称及 keycode 核对，以及 SDK 37 AIDL 编译器生成 Java/NDK 接口与冻结 API 相等检查；板上验收入口为 `adb shell getevent -lt`、`dumpsys input` 和电视主页的学习向导。

`python3 scripts/validate-cec-lifecycle.py --report records/cec-lifecycle-validation.json` 在主机编译实际 CEC 输入源码，以适配器和系统调用夹具检查信号退出、崩溃后接管、他方配置保护、EBUSY 重试及失败返回。关闭开关的板上验收还应检查 `CEC_ADAP_G_LOG_ADDRS` 的地址数和地址掩码归零，并确认电视遥控不再产生输入事件；内核保留的 passthrough 标志在没有逻辑地址时不会转发按键。
