# RK3399 既有应用迁移

我保留原系统中六个第三方应用，复用已经取得并验证的原始 APK，不重新下载、
修改或签名。YouTube 入口只使用官方客户端，SmartTube 不进入本次私有清单。
公开仓库没有这些 APK；以下是可复现的暂存方式和验收边界。

| 应用 | 包名 | 版本 | 本次原生库 |
| --- | --- | --- | --- |
| CMFA | `com.github.metacubex.clash.meta` | 2.11.35.Meta / 211035 | ARM64、ARMv7 |
| Kodi | `org.xbmc.kodi` | 21.3 / 2103000 | ARMv7 |
| 云视听小电视 | `com.xiaodianshi.tv.yst` | 1.8.9 / 108900 | ARMv7 |
| 银河奇异果 | `com.gitvdemo.video` | 16.9.0.221245 / 221245 | ARMv7 |
| 酷喵 | `com.cibn.tv` | 13.0.1.3 / 2131300103 | armeabi |
| BV | `dev.aaa1115910.bv` | 0.2.9.r693.f86ceda.release / 693 | ARM64、ARMv7 |

RK3399 产品同时提供 ARM64 和 ARM32 用户空间。旧产品目录只准备了 ARM32
原生库，直接复制会遗漏 CMFA、BV 原始通用 APK 中的 ARM64 库。我从每个
原始 APK 重新提取对应字节，分别放进应用自身的 `lib/arm64` 和 `lib/arm`。
32 位应用仍然运行在 32 位进程里，不被重新编译或误标为 64 位。

每个 APK 的完整 SHA-256 必须与原有签名和来源验证记录一致，才会进入暂存。
我保留其原证书证据、来源页面、相关许可，以及 CMFA、Kodi、BV 的对应源码
归档。这里复用的是与确切文件哈希绑定的既有签名证据，不宣称已经重新完成
RK3399 上的安装与运行测试。

生成器使用 `Rk3399Legacy*` 模块名，重新生成 `Android.bp` 与 `Android.mk`，
避免把旧产品的模块重复注册。银河奇异果明确依赖 `android.test.runner`，
生成的产品清单会加入该库。所有 APK 保持原始签名，所有旁置原生文件与 APK
成员逐字节一致；没有修改签名、ZIP 布局或应用清单。

这些旧应用沿用原项目的预装例外：签名 APK 内的 JNI 经过压缩，系统镜像中
另放匹配的原生库，因此 `preprocessed` 检查例外仍被明确记录。不能把这个
例外描述成检查通过。官方 YouTube 使用单独的一次性 PackageInstaller
方案，不使用上述例外。

在 Linux 构建机生成独立目录：

```sh
python3 scripts/stage-rk3399-legacy-apps.py \
  --source /private/original-verified/apps \
  --stage /private/stage/legacy-private \
  --aapt2 /path/to/aosp/out/host/linux-x86/bin/aapt2
```

输入目录必须保留原来的 `records/`、`licenses/` 和 `sources/`。目标目录
必须尚不存在。生成完成后，先检查 `manifest.json`，再由构建者把目录复制到
`device/firefly/rk3399/apps/legacy-private/`。这个私有目录已被 Git 忽略，
缺失时公开产品不包含六个 APK。

原生库检查覆盖 ARM/AArch64 ELF 类型、原始字节和 `DT_NEEDED`。部分受保护
的发行库没有正常的 ELF section table；生成器从运行时使用的 program
headers 读取动态依赖，保存 `readelf` 的 section 警告，避免把它误报为没有
依赖。新 ARM64 系统库的完整符号解析仍需等产品输出完成后核对，不能用旧
ARM32 的结果替代。

保留的已知限制：

- Kodi 21.3 ARM32 的可选 Vorbis CD 编码插件缺少 11 个 `oggpack_*` 符号。
  原检查中播放主库及其他 83 个原生库通过；这不等于 H.264/HEVC 播放失败。
- BV 保留上游的地区限制；本次没有更改该行为。
- 酷喵保留 armeabi、target SDK 25 及三个以 `.so` 命名的 SecurityGuard ZIP
  插件。这三个文件是原始插件数据，不伪称 ELF 库。
- 登录、DRM、受保护内容、运行时插件与 RK3399 实际播放仍需真机验收。
