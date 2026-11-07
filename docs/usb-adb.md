> 历史 bring-up 资料。当前构建与验收范围以 [BUILD.md](../BUILD.md) 和独立移植复盘为准。旧 alpha、TF、HEVC 与旧校验项不代表当前发布已验证状态；当前 HEVC 硬件节点停用，最终板上验收介质为 eMMC。

# USB gadget 与 ADB 默认监听行为

本板使用原版 RK3288 的 `ff580000.usb` OTG 设备控制器。USB-A host 口用于
键鼠，OTG Micro-USB 口用数据线连接电脑。默认 USB 功能为 `adb`，
`ro.adb.secure=1` 保留电脑密钥认证；第一次连接需要在 HDMI 界面批准授权。

## 初始化顺序

`init.fireflyrk3288.rc` 的 `early-init` 选择 OTG 控制器。`on init` 随后创建
`/config/usb_gadget/g1`、USB descriptors、语言字符串、`functions/ffs.adb`、
`configs/b.1` 和 `/dev/usb-ffs/adb`，以 shell UID/GID 挂载 FunctionFS，
最后设置 `sys.usb.configfs=1`。板级文件不直接启动 adbd，也不直接写 UDC。

以下顺序依据固定的 `android-17.0.0_r1` 源码：

- `system/core/init/init.cpp` 的 `LoadBootScripts` 首先解析
  `/system/etc/init/hw/init.rc`。该文件显式导入板级 hardware rc 及两份公共 USB rc。
- `Parser::ParseData` 在 EOF 先完成最后一个 section，再调用各 parser 的 `EndFile`。
  `ImportParser::EndFile` 此时才解析收集的 import，所以根文件 `on init` 的
  configfs mount 先于板级 `on init` 注册。
- `ActionManager::AddAction` 按注册顺序追加 action；`ExecuteOneCommand` 按此顺序
  将同一事件的 action 入队并逐条执行。因此根文件的
  `mount configfs none /config nodev noexec nosuid` 先于板级 gadget 创建。
- 公共 `init.usb.rc` 在 boot 从 `persist.sys.usb.config` 设置 `sys.usb.config`。
  `init.usb.configfs.rc` 在 `adb` + `configfs=1` 时启动 adbd。
- adbd 打开 FunctionFS ep0 并写入 descriptors/strings，随后设置
  `sys.usb.ffs.ready=1`；公共 configfs rc 再链接 `ffs.adb` 并写 UDC 绑定控制器。
  `none` 路径先解绑、停止 adbd，再复位 `ffs.ready`。

这是创建与绑定时序；FunctionFS 挂载、控制器 probe、线材及主机枚举结果仍由首启日志确认。

## USB 挂载失败时保持默认无网络监听

上游 adbd 在启动时检查 `/dev/usb-ffs/adb/ep0`。该路径不存在、且没有显式配置
监听地址/正 TCP 端口时，上游会自动监听 TCP 和 VSOCK 5555。
`service.adb.tcp.port=-1` 也会落入这一分支。仅在 rc 中延后或 gate 启动仍不够：
框架的 `AdbService` 可以独立执行 `ctl.start adbd`，init 的 mount 失败也不会中止
后面的 rc 命令。

`patches/0001-adbd-disable-implicit-network-fallback.patch` 删除这一自动 fallback，
同时删除已无用途的 `is_usb` 局部变量。USB 初始化、显式
`service.adb.listen_addrs`、`service.adb.tcp.port`、`persist.adb.tcp.port` 及
主机密钥认证代码保持原逻辑。结果是默认配置中 ep0 缺失时 adbd 不创建网络监听；
需要网络 ADB 时仍必须显式配置相应地址或端口。

补丁以 `platform/packages/modules/adb` 提交
`9084198a2d4b0f6a0f174260fb42da33485b684d` 为基础，安装器先核对 HEAD，
再用正向/反向 `git apply --check` 识别未应用、已应用及冲突状态。

## 已执行的验证

`scripts/test-adbd-usb-default.py` 在临时 Git 树中运行真实安装脚本，验证首次应用、
重复应用、冲突时不覆盖本地文件及错误 HEAD 拒绝。它再分别从固定源码与应用补丁后的
`main.cpp` 提取实际 USB/监听选择代码块，用主机 C++ 编译器编译并执行：

- ep0 存在/缺失，默认配置与负/零/无效端口。
- 显式服务端口、持久端口及服务端口优先级。
- 显式 UNIX socket、TCP/VSOCK 地址及地址对端口的优先级。

每份源码执行 12 种输入。缺 ep0 的默认输入在原源码中产生
`tcp:5555`、`vsock:5555`，补丁后产生空监听列表；正常 USB 和显式配置案例通过。
测试还逐字比较认证前缀与监听选择后的源码，确认这些部分未变。
结果及 SHA-256 见 `records/usb-adbd-failclosed-test.json`。

该验证实际运行主机上的源码块，property 查询、ep0 状态及启动监听的副作用由
fixture 提供。完整构建及后续 `build-06` 增量构建结束后，已经对实际安装产物
单独执行 APEX 验证，49 项检查通过：从 `com.android.adbd.capex` 提取的
ELF32 ARM adbd 与本次编译及 APEX staging 的 SHA-256 一致；安装的板级 init
和 ueventd 文件也与 port 源码及 AOSP 输入三方一致。实际生成属性包含
`ro.adb.secure=1` 和 `persist.sys.usb.config=adb`。

构建产物记录见
`usb-build-artifact-validation.json`（本地历史证据：`records/usb-build-artifact-validation.json`，未随源码发布）。
随后对实际 Android 文件系统分区的 325 项集中检查也已通过，包含从 system.img
读取的 adbd CAPEX，见
`android-partitions-focused.json`（本地历史证据：`records/android-partitions-focused.json`，未随源码发布）。
`verify-sd.py` 随后单独读取 TF/eMMC 完整整盘，分别通过 520/520、522/522 项，
其中包含实际 system 分区中的 adbd CAPEX 检查。板上 USB 枚举及首次密钥授权
记录在首启阶段收集。

## 最终系统中的 adbd 入包验证

`verify-sd.py` 从实际整盘的 system 文件系统提取 `com.android.adbd.capex`，
调用 `scripts/verify-adbd-apex.py` 的核心函数。它核对固定补丁后的 `main.cpp`
SHA-256、ARM APEX 变体的编译/链接依赖及 Ninja 成功记录，然后用本次构建的
`deapexer` 提取 CAPEX，比较三个 `bin/adbd` 的 SHA-256：最终 CAPEX payload、
`android_arm_armv7-a-neon_cortex-a15_apex31/adbd`、APEX staging
`image.apex/bin/adbd`。输入 CAPEX 还须与本次生成和安装的 CAPEX 完全一致。

缺少对象、链接产物、CAPEX、工具或成功日志记录时验证失败。Ninja 对同一规则的
多个输出记录共同的最大 output mtime；因此校验器同时读取显式和隐式输出，要求
每个输出都有相同的成功命令记录，日志时间严格等于所有实际输出时间的最大值。
不使用时间容差；无法精确对应的 restat 记录也会拒绝。源、对象、链接及 strip
产物的时间顺序另行核对；验证期间的输入、同规则输出、生成图及 Ninja 日志须
保持不变。完整 Android 构建结束后再执行此检查。

`scripts/test-adbd-ninja-evidence.py` 用 AOSP 实际 Ninja 二进制创建带隐式输出的
两输出规则，复现共同最大时间和 unchanged-restat 的日志行为，并检查 1 ns
时间偏差、错误命令记录及缺失输出记录会被拒绝。8 项检查的结果见
`records/adbd-ninja-evidence-test.json`。

需要单独检查已提取的 CAPEX 时，在 `port/` 运行。以下示例使用与 AOSP 构建
相同的容器，将 CAPEX 放在工作根可访问的位置，scratch 父目录须已存在：

```sh
port_root=$(pwd -P)
work_root=$(dirname -- "$port_root")
adb_verify_builder=${FIREFLY_ANDROID_BUILDER_IMAGE:-firefly-android17-builder:20261104}
docker run --rm --init --user "$(id -u):$(id -g)" \
  --volume "$work_root:$work_root" --workdir "$port_root" \
  "$adb_verify_builder" python3 scripts/verify-adbd-apex.py \
  --aosp "$work_root/aosp" \
  --capex "$work_root/artifacts/com.android.adbd.capex" \
  --report "$work_root/artifacts/new-adbd-apex-report.json" \
  --scratch-dir "$work_root/artifacts"
```

CAPEX 文件名不影响识别。脚本使用构建目录的 `deapexer`，优先使用同目录的
`debugfs_static` 和 `fsck.erofs`，也可使用宿主机已有的对应工具。它在 scratch
目录内新建子目录并保留提取文件；已有 JSON 报告不会被覆盖。
