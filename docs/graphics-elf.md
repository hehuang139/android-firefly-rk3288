> 历史 bring-up 资料。当前构建与验收范围以 [BUILD.md](../BUILD.md) 和独立移植复盘为准。旧 alpha、TF、HEVC 与旧校验项不代表当前发布已验证状态；当前 HEVC 硬件节点停用，最终板上验收介质为 eMMC。

# 图形 ELF 依赖检查

`scripts/verify-graphics-elf.py` 检查最终产品目录里的 Mesa、minigbm mapper、
allocator 和 DRM composer。检查内容包括 ARM32/EABI5、Android 动态链接器、
`DT_NEEDED`、非弱未定义符号及其版本，以及 EGL/GLES 和 mapper 必需导出。

先完成正常产品构建，再运行：

```sh
python3 port/scripts/verify-graphics-elf.py \
  --aosp /path/to/aosp \
  --product-out /path/to/aosp/out/target/product/rk3288 \
  --report graphics-elf-report.json
```

成功报告具有 `result: PASS`、`passed: true` 和 `graphics_verified: true`。
失败退出码为 1，JSON 中给出缺失文件、无法解析的依赖或具体符号。
用 `--work-dir` 指定一个现有空目录，可保留解包后的 APEX 和生成的
`linkerconfig/ld.config.txt`；未指定时使用临时目录。

## 最终输入

检查器从 `product-out` 读取以下路径：

- `vendor/lib/egl/libEGL_mesa.so`、`libGLESv1_CM_mesa.so`、`libGLESv2_mesa.so`。
- `vendor/lib/libgallium_dri.so`、`libminigbm_gralloc.so`。
- `vendor/lib/hw/mapper.minigbm.so`。
- `vendor/bin/hw/android.hardware.graphics.allocator-service.minigbm`。
- `vendor/bin/hw/android.hardware.composer.hwc3-service.drm`。
- `system/bin/linker` 及安装的符号链接目标。
- `system`、`system_ext`、`product`、`vendor` 内实际依赖的库与属性文件。
- `system/etc/linker.config.pb`、`llndk.libraries.txt`、`sanitizer.libraries.txt`，
  以及各分区安装的 `linker.config.pb`、`public.libraries.txt`。
- 各分区 `apex/` 内安装的 `.apex`、`.capex` 包。脚本重新解包这些包，
  记录归档 SHA-256，使用解包后的实际库。`com.android.runtime` 中的 bionic
  路径由安装的 Android 符号链接解析。

运行 `--requirements` 可打印完整入口清单；这个模式只列需求。

## 主机工具

脚本使用固定 AOSP 标签的 `build/make/tools/check_elf_file.py` 中的 ELF
符号解析器，以及产品构建所用 `clang-r584948b/bin/llvm-readobj`。主机构建还需生成：

```text
out/host/linux-x86/bin/linkerconfig
out/host/linux-x86/bin/deapexer
out/host/linux-x86/bin/debugfs_static
out/host/linux-x86/bin/fsck.erofs
```

项目的 `./build.sh build` 同时构建这些工具及 init 校验用的
`host_init_verifier`。已有产品输出只需补工具时，在 `port/` 执行
`./build.sh tools`。`--check-tools` 检查上述四个图形工具及固定解析器，
成功结果为 `TOOLS_READY`，该模式只报告工具可用性。

## namespace 和符号范围

脚本用最终分区 metadata 和解包的 APEX，在临时 Android 根目录运行同标签
host `linkerconfig --treblelize`，据此使用实际 `search.paths`、
`permitted.paths` 和 namespace link 的库名允许列表。
这与 init 的全局 `GenerateLinkerConfiguration()` 一致；它不传 `--strict`。
上游系统 metadata 同时列出 release/debug ART 库，安装的 release ART APEX
只提供其自身库。init 仅在单独更新指定 `--apex` 时使用 `--strict`。
检查器仍要求每个实际 ELF 的全部 `DT_NEEDED`、非弱符号和符号版本可解析。
版本匹配遵循 Bionic：提供库定义了请求版本时，符号须精确匹配；该库未定义
请求版本时，可由其 unversioned global 符号满足。报告逐项记录这类匹配。
例如 LLNDK stub 中的 `sync_wait@LIBSYNC` 对应系统 `libsync.so` 的 global
导出，系统实现本身没有 `LIBSYNC` version definition。

EGL/GLES、Gallium 和 mapper 在 `system/sphal` 中检查；allocator/composer
在 `vendor/default` 中检查。namespace 间只能使用其 link 导出的库。
被导出的系统库所依赖的私有系统库留在自己的 namespace；其内部符号不会
自动暴露给 SP-HAL。运行时 linker 的 `ld-android.so` 入口使用实际安装的
ARM linker 文件。

Mesa 的 EGL/GLES 安装名有 `_mesa` 后缀；根驱动允许保留原始 `DT_SONAME`。
当前产品使用 minigbm allocator/mapper，配置关闭 Mesa GBM，因此根集合不要求
独立的 `libgbm.so`。所有实际 `DT_NEEDED` 依赖仍按 namespace 严格解析。
依赖按照请求的文件名和 namespace 查找，不扫描全产品目录选择同名文件。
所有参与检查的 ELF 均来自安装分区或本次解包的 APEX。

该检查验证实际文件的链接依赖。整卡检查中的分区字节/SHA-256 对照将产品
文件与最终镜像相连；板上 GPU 分配、渲染和 HDMI 输出记录在首启结果中。

## 检查器自身验证

```sh
python3 port/scripts/test-graphics-elf.py \
  --aosp /path/to/aosp \
  --report graphics-elf-fixture-test.json
```

该命令用固定工具链实际链接独立 ARM 共享库，覆盖符号版本不匹配、缺少
非弱符号、可选弱符号、namespace 限制、私有依赖隔离、Mesa 安装名和 APEX
绝对符号链接等路径。它的结果与最终产品检查报告分别记录。

实际产品检查记录在
`records/graphics-elf-product-validation.json`（本地历史证据：`records/graphics-elf-product-validation.json`，未随源码发布）：
8 个图形入口、41 个安装 APEX 和 71 个不同 ELF 均通过。
实际 Android 文件系统分区的集中检查也已通过，在
`android-partitions-focused.json`（本地历史证据：`records/android-partitions-focused.json`，未随源码发布） 中记录
117 个普通输入文件及 5 个 APEX 内依赖文件的哈希对照。TF/eMMC 完整整盘
校验也已分别通过 520/520、522/522 项，包含这些图形输入与实际分区的哈希对照。
最新 14 项独立 ARM fixture 结果在
`graphics-elf-fixture-test-v2.json`（本地历史证据：`records/graphics-elf-fixture-test-v2.json`，未随源码发布）；
先前 11 项报告保留。运行时语义修正、源码依据和前两次检查结果见
`graphics-elf-runtime-semantics-validation.json`（本地历史证据：`records/graphics-elf-runtime-semantics-validation.json`，未随源码发布）。
