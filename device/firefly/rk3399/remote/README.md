# Firefly-RK3399 电视输入候选

USB HID 键盘、鼠标和遥控器使用通用 Android 输入路径。沿用的红外学习服务和
`gpio_ir_recv` 键布局是可复用的软件组件；原版 RK3399 的实际接收器节点、
遥控码表和唤醒行为尚未通过实机验收。没有接收器时返回 `ir_unavailable`。
不要按 RK3288 的 GPIO 编号给 RK3399 接线或修改设备树。

默认码表保留旧系统的 Firefly 12 键 NEC 配置，供确认兼容的遥控器使用。
该表来源于旧板官方资料，不能据此宣称新板接收器已可用。

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

`firefly-cec-input` 提供 Linux CEC playback 地址与 rc-core 按键路径，默认禁用。
RK3399 的 HDMI CEC 引脚、内核节点与电视端行为必须在新板单独确认；不得套用
旧板的 GPIO7_C0 或 GPIO7_C7 配置。完整 Android HDMI 控制、ARC/eARC 和认证
不由这项输入服务提供。
