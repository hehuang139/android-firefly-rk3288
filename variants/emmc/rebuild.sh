#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Build files only: no block-device or board access.
set -euo pipefail
variant_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
port_root=$(cd -- "$variant_root/../.." && pwd)
build_image=${FIREFLY_EMMC_BUILD_IMAGE:-firefly-rk3288-uboot-builder:local}
jobs=${FIREFLY_EMMC_JOBS:-2}
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'Invalid job count' >&2; exit 2; }
docker image inspect "$build_image" >/dev/null
mkdir -p "$variant_root/out/downloads" "$variant_root/out/source" "$variant_root/bootloader" "$variant_root/boot" "$variant_root/records" "$variant_root/configs"
archive="$variant_root/out/downloads/u-boot-v2024.01.tar.gz"
if [[ ! -f "$archive" ]]; then
  curl -fL --retry 3 https://codeload.github.com/u-boot/u-boot/tar.gz/refs/tags/v2024.01 -o "$archive"
fi
printf '%s  %s\n' a03c3c2ba9d2bea5176c6406f1f3429a79e1147be242f5a07dbd9e89b3cc83c4 "$archive" | sha256sum -c -
src="$variant_root/out/source/u-boot-2024.01"
[[ -d "$src" ]] || tar -xzf "$archive" -C "$variant_root/out/source"
for change in "$variant_root"/patches/*.patch; do
  if patch -d "$src" -p1 --forward --dry-run --batch < "$change" >/dev/null 2>&1; then
    patch -d "$src" -p1 --forward --batch < "$change"
  elif ! patch -d "$src" -p1 --reverse --dry-run --batch < "$change" >/dev/null 2>&1; then
    echo "Patch conflict: $change" >&2; exit 1
  fi
done
docker run --rm --init --user "$(id -u):$(id -g)" \
  -e SOURCE_DATE_EPOCH=1704672000 -e FIREFLY_EMMC_JOBS="$jobs" \
  -v "$port_root:/port" -w /port/variants/emmc "$build_image" bash -c '
    set -euo pipefail
    cd out/source/u-boot-2024.01
    make CROSS_COMPILE=arm-linux-gnueabihf- O=/port/variants/emmc/out/uboot firefly-rk3288_defconfig
    scripts/config --file /port/variants/emmc/out/uboot/.config \
      --disable ENV_IS_IN_MMC --enable ENV_IS_NOWHERE \
      --disable SILENT_CONSOLE --enable BOOTSTD_FULL --enable CMD_SYSBOOT \
      --enable MISC --enable ROCKCHIP_EFUSE --enable MISC_INIT_R \
      --enable HASH --enable SHA256 --disable CMD_FUSE \
      --disable MMC_HS200_SUPPORT --disable MMC_HS400_SUPPORT \
      --set-val BOOTDELAY 5 --set-str LOCALVERSION "-firefly-android-emmc1"
    python3 /port/variants/emmc/scripts/set-bootcommand.py /port/variants/emmc/out/uboot/.config
    make CROSS_COMPILE=arm-linux-gnueabihf- O=/port/variants/emmc/out/uboot olddefconfig
    make -j"$FIREFLY_EMMC_JOBS" CROSS_COMPILE=arm-linux-gnueabihf- O=/port/variants/emmc/out/uboot
    dtc -I dts -O dtb -b 0 -o /port/variants/emmc/boot/rk3288-firefly-android.dtb /port/kernel/final/device-tree/rk3288-firefly-es8323-npll216.decompiled.dts
  ' 2>&1 | tee "$variant_root/records/build.log"
cp "$variant_root/out/uboot/.config" "$variant_root/configs/uboot.config"
cp "$port_root/kernel/final/firefly-rk3288-final.config" "$variant_root/configs/kernel.config"
install -m 644 "$variant_root/out/uboot/idbloader.img" "$variant_root/bootloader/idbloader.img"
install -m 644 "$variant_root/out/uboot/u-boot-dtb.img" "$variant_root/bootloader/u-boot-dtb.img"
printf '%s  %s\n' 2021fedaf9241b18d8184191c24a740f05beaceac0aeffb80c41376e1c815c5b "$variant_root/boot/rk3288-firefly-android.dtb" | sha256sum -c -
python3 "$variant_root/tests/test-identity-init.py" --image "$build_image"
(cd "$variant_root" && sha256sum boot/rk3288-firefly-android.dtb boot/extlinux.conf bootloader/idbloader.img bootloader/u-boot-dtb.img > SHA256SUMS)
echo 'Built eMMC loader and final DTB files. Board and whole-image validation are separate.'
