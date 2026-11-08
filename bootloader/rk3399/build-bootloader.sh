#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Build original-board TPL/SPL/U-Boot and TF-A from fixed sources; no flash.
set -euo pipefail
package_dir=$(cd -- "$(dirname -- "$0")" && pwd)
uboot_archive=$(realpath "${1:?u-boot-v2024.01.tar.gz}")
tfa_archive=$(realpath "${2:?arm-trusted-firmware-v2.10.tar.gz}")
build_root=${3:?A new output directory is required}
jobs=${4:-4}
printf '%s  %s\n' a03c3c2ba9d2bea5176c6406f1f3429a79e1147be242f5a07dbd9e89b3cc83c4 "$uboot_archive" | sha256sum -c -
printf '%s  %s\n' 2e18b881ada9198173238cca80086c787b1fa3f698944bde1743142823fc511c "$tfa_archive" | sha256sum -c -
test ! -e "$build_root" || { echo 'Output exists; use a new directory.' >&2; exit 1; }
mkdir -p "$build_root/src" "$build_root/assets"
build_root=$(realpath "$build_root")
tar -xzf "$uboot_archive" -C "$build_root/src"
tar -xzf "$tfa_archive" -C "$build_root/src"
export SOURCE_DATE_EPOCH=1794096000 TZ=UTC
export KBUILD_BUILD_USER=firefly KBUILD_BUILD_HOST=builder
export PYTHONDONTWRITEBYTECODE=1
# Ubuntu's Linux ARM cross compiler defaults to PIE. M0 is a freestanding
# Cortex-M0 image; use a no-PIE wrapper without changing upstream TF-A source.
mkdir "$build_root/m0-toolchain"
printf '#!/bin/sh\nexec arm-linux-gnueabihf-gcc -fno-pie -no-pie "$@"\n' > "$build_root/m0-toolchain/m0-gcc"
chmod 0755 "$build_root/m0-toolchain/m0-gcc"
for tool in cpp ar objcopy objdump nm; do
    ln -s "$(command -v arm-linux-gnueabihf-$tool)" "$build_root/m0-toolchain/m0-$tool"
done
make -C "$build_root/src/arm-trusted-firmware-2.10" -j"$jobs" PLAT=rk3399 CROSS_COMPILE=aarch64-linux-gnu- M0_CROSS_COMPILE="$build_root/m0-toolchain/m0-" BUILD_BASE="$build_root/tfa" bl31
source_dir="$build_root/src/u-boot-2024.01"
output="$build_root/uboot"
# The first Android candidate is deliberately eMMC-only after BootROM selects
# this loader. It never probes a similarly named TF partition as fallback.
python3 - "$source_dir" <<'PY'
from pathlib import Path
import sys
r=Path(sys.argv[1]);p=r/'arch/arm/dts/rk3399-firefly-u-boot.dtsi';s=p.read_text()
old='u-boot,spl-boot-order = "same-as-spl", &sdhci, &sdmmc;'
assert s.count(old)==1;p.write_text(s.replace(old,'u-boot,spl-boot-order = &sdhci;'))
p=r/'include/configs/rockchip-common.h';s=p.read_text();old='#define BOOT_TARGETS\t"mmc1 mmc0 nvme scsi usb pxe dhcp spi"'
assert s.count(old)==1;p.write_text(s.replace(old,'#define BOOT_TARGETS\t"mmc0"'))
p=r/'include/configs/rk3399_common.h';s=p.read_text();old='kernel_addr_r=0x02080000'
assert s.count(old)==1;p.write_text(s.replace(old,'kernel_addr_r=0x02000000'))
PY
make -C "$source_dir" O="$output" CROSS_COMPILE=aarch64-linux-gnu- firefly-rk3399_defconfig
"$source_dir/scripts/kconfig/merge_config.sh" -m -O "$output" "$output/.config" "$package_dir/firefly-android.config"
make -C "$source_dir" O="$output" CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make -C "$source_dir" O="$output" CROSS_COMPILE=aarch64-linux-gnu- BL31="$build_root/tfa/rk3399/release/bl31/bl31.elf" -j"$jobs"
cp "$output/idbloader.img" "$output/u-boot.itb" "$output/u-boot-rockchip.bin" "$output/u-boot.dtb" "$build_root/assets/"
cp "$build_root/tfa/rk3399/release/bl31/bl31.elf" "$build_root/assets/"
"$output/tools/dumpimage" -l "$output/u-boot.itb" > "$build_root/fit-list.txt"
python3 "$package_dir/validate-bootloader.py" "$build_root"
