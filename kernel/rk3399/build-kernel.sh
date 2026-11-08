#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Isolated mainline ARM64 build. Never writes a block device.
set -euo pipefail
package_dir=$(cd -- "$(dirname -- "$0")" && pwd)
archive=$(realpath "${1:?linux-6.18.60.tar.xz is required}")
build_root=${2:?A new output directory is required}
jobs=${3:-4}
printf '%s  %s\n' 3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e "$archive" | sha256sum -c -
test ! -e "$build_root" || { echo 'Output exists; use a new directory.' >&2; exit 1; }
mkdir -p "$build_root"
build_root=$(realpath "$build_root")
tar -xJf "$archive" -C "$build_root"
source_dir="$build_root/linux-6.18.60"
output="$build_root/build"
mkdir "$output"
cp "$package_dir/rk3399-firefly-android.dts" "$source_dir/arch/arm64/boot/dts/rockchip/"
export KBUILD_BUILD_TIMESTAMP='2026-11-08 00:00:00 UTC'
export KBUILD_BUILD_USER=firefly KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1
make -C "$source_dir" O="$output" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- defconfig
# Drop unrelated SoC families while preserving upstream ARM64 defaults.
python3 - "$output/.config" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]);s=p.read_text()
families=re.findall(r'^CONFIG_ARCH_([A-Z0-9_]+)=y$',s,re.M)
# Only actual multi-platform vendor switches; never disable generic ARCH_* helpers.
vendors={'ACTION','SUNXI','ALPINE','APPLE','BCMBCA','BCM2835','BCM_IPROC','BERLIN','BLAIZE','EXYNOS','HIBMC','HISI','K3','KEEMBAY','LG1K','MA35','MESON','MVEBU','MXC','NPCM','NXP','LAYERSCAPE','LPC18XX','QCOM','REALTEK','RENESAS','SEATTLE','SOPHGO','SPACEMIT','SPRINT','STRATIX10','STM32','SYNQUACER','TEGRA','TESLA_FSD','THUNDER','THUNDER2','UNIPHIER','VEXPRESS','VISCONTI','XGENE','ZYNQMP','MEDIATEK'}
for name in families:
 if name in vendors:s=s.replace(f'CONFIG_ARCH_{name}=y',f'# CONFIG_ARCH_{name} is not set')
p.write_text(s)
PY
KCONFIG_CONFIG="$output/.config" "$source_dir/scripts/kconfig/merge_config.sh" -m -O "$output" "$output/.config" "$package_dir/android.config"
python3 "$package_dir/select-modules.py" "$output/.config"
make -C "$source_dir" O="$output" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
python3 "$package_dir/validate-kernel.py" --config-only "$build_root"
make -C "$source_dir" O="$output" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j"$jobs" Image rockchip/rk3399-firefly-android.dtb modules
python3 "$package_dir/validate-kernel.py" "$build_root"
