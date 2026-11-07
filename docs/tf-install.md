> Historical bring-up reference. For the final tested eMMC source profile and
> current validation limits use BUILD.md and docs/移植复盘.md. Old check counts
> and TF/HEVC instructions below are not current release validation.

# TF 卡刷写与 HDMI 首启

准备至少 **16 GB** 的 TF 卡、读卡器、HDMI 显示器、USB 键鼠和网线。
镜像为 12 GiB 整盘布局，刷写会清空所选 TF 卡。

1. 从工作根 `tvbox-artifacts/` 取得
   `firefly-rk3288-tv-android17-sd-alpha.img.xz` 和 `SHA256SUMS`。
   确认 `build-status.json` 的本轮镜像、校验和压缩步骤完成；TF 的实际整盘
   报告为 `image-validation.json`。当前已完成的 TF 检查为 518/518 项通过。
2. 校验文件的 SHA-256 与 `SHA256SUMS` 中同名一行一致。Linux 可在文件目录运行：

   ```sh
   sha256sum firefly-rk3288-tv-android17-sd-alpha.img.xz
   ```

3. 打开 [balenaEtcher](https://etcher.balena.io/)，选择 **Flash from file**，
   直接选上述 `.img.xz`；Etcher 支持边解压边写入。选择读卡器中的 TF 卡，
   按容量和设备名称核对目标，再执行 **Flash**，等待写后验证完成。
   如电脑提示格式化新分区，取消提示并安全弹出卡。
4. 板卡断电，插入 TF 卡，连接并打开 HDMI 显示器，USB host 接键鼠，接网线，
   最后连接板卡电源。记录首次画面、出现画面的等待时间和最终进入的位置。
5. 进入 Firefly TV 后，先播放内置 H.264 / H.265 测试片并查看硬解检查，再试
   本地视频与直播；家长模式在设置 PIN 后启用。首启日志和 USB ADB 授权见
   [首启指南](first-boot.md)。

本 TF 变体的 Linux 设备树关闭 eMMC 控制器。若插卡后仍进入旧系统，或一直
没有 HDMI 画面，记录电源、LED、显示器信号和按键现象，保留原 eMMC，继续排查
板载加载器是否选择 TF。此时不要擦除 eMMC 或尝试未知 Loader 写入命令。

安装到 eMMC 使用独立的 `firefly-rk3288-tv-android17-emmc-alpha.img`；先按
[eMMC 安装指南](emmc-install.md) 识别 Loader、地址映射、容量并完成备份。
