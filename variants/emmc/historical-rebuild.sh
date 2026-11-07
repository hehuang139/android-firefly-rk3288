#!/bin/bash
echo "Historical bring-up script; use rebuild.sh." >&2
exit 2
#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
# This script builds ordinary files. It never opens a host block device.
variant_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
port_root=$(cd -- "$variant_root/../.." && pwd)
build_image=${FIREFLY_EMMC_BUILD_IMAGE:-firefly-rk3288-uboot-builder:local}
build_jobs=${FIREFLY_EMMC_JOBS:-2}
[[ "$build_jobs" =~ ^[12]$ ]] || { echo 'FIREFLY_EMMC_JOBS must be 1 or 2' >&2; exit 2; }
docker image inspect "$build_image" >/dev/null 2>&1 || {
    echo "Build environment not found: $build_image" >&2
    echo 'Run: docker build -t firefly-rk3288-uboot-builder:local bootloader/source' >&2
    exit 1
}
variant_cpu_set=$(python3 -c 'import os; print(",".join(map(str, sorted(os.sched_getaffinity(0))[-2:])))')
mkdir -p "$variant_root/out/downloads" "$variant_root/out/source" "$variant_root/records" "$variant_root/configs" "$variant_root/bootloader" "$variant_root/boot"
python3 "$variant_root/scripts/snapshot-shared.py"

kernel_archive="$port_root/kernel/downloads/linux-6.18.60.tar.xz"
uboot_archive="$port_root/bootloader/source/u-boot-v2024.01.tar.gz"
if [[ ! -f "$kernel_archive" ]]; then
    kernel_archive="$variant_root/out/downloads/linux-6.18.60.tar.xz"
    [[ -f "$kernel_archive" ]] || curl -fL --retry 3 https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.18.60.tar.xz -o "$kernel_archive"
fi
if [[ ! -f "$uboot_archive" ]]; then
    uboot_archive="$variant_root/out/downloads/u-boot-v2024.01.tar.gz"
    [[ -f "$uboot_archive" ]] || curl -fL --retry 3 https://codeload.github.com/u-boot/u-boot/tar.gz/refs/tags/v2024.01 -o "$uboot_archive"
fi
printf '%s  %s\n' 3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e "$kernel_archive" | sha256sum -c -
printf '%s  %s\n' a03c3c2ba9d2bea5176c6406f1f3429a79e1147be242f5a07dbd9e89b3cc83c4 "$uboot_archive" | sha256sum -c -

# Extract private source trees; the TF sources/build outputs remain untouched.
if [[ ! -d "$variant_root/out/source/linux-6.18.60" ]]; then
    tar -xJf "$kernel_archive" -C "$variant_root/out/source"
fi
if [[ ! -d "$variant_root/out/source/u-boot-2024.01" ]]; then
    tar -xzf "$uboot_archive" -C "$variant_root/out/source"
fi
for change in "$variant_root"/patches/*.patch; do
    if patch -d "$variant_root/out/source/u-boot-2024.01" -p1 --forward --dry-run --batch < "$change" >/dev/null 2>&1; then
        patch -d "$variant_root/out/source/u-boot-2024.01" -p1 --forward --batch < "$change"
    elif ! patch -d "$variant_root/out/source/u-boot-2024.01" -p1 --reverse --dry-run --batch < "$change" >/dev/null 2>&1; then
        echo "Patch does not match private source: $change" >&2; exit 1
    fi
done
cp "$variant_root/rk3288-firefly-android17-emmc.dts" "$variant_root/out/source/linux-6.18.60/arch/arm/boot/dts/rockchip/"
if ! rg -q '^dtb-\$\(CONFIG_ARCH_ROCKCHIP\) \+= rk3288-firefly-android17-emmc.dtb$' "$variant_root/out/source/linux-6.18.60/arch/arm/boot/dts/rockchip/Makefile"; then
    printf '%s\n' 'dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3288-firefly-android17-emmc.dtb' >> "$variant_root/out/source/linux-6.18.60/arch/arm/boot/dts/rockchip/Makefile"
fi
cp "$port_root/kernel/final/firefly-rk3288-final.config" "$variant_root/configs/kernel.config"
mkdir -p "$variant_root/out/kernel"
cp "$variant_root/configs/kernel.config" "$variant_root/out/kernel/.config"

docker run --rm --init --user "$(id -u):$(id -g)" --cpus=2 --cpuset-cpus="$variant_cpu_set" \
    -e SOURCE_DATE_EPOCH=1704672000 -e FIREFLY_EMMC_JOBS="$build_jobs" \
    -e KBUILD_BUILD_TIMESTAMP='2026-10-30 00:00:00 UTC' \
    -e KBUILD_BUILD_USER=firefly -e KBUILD_BUILD_HOST=builder -e KBUILD_BUILD_VERSION=1 \
    -v "$port_root:/port" -w /port/variants/emmc "$build_image" bash -c '
      set -euo pipefail
      make -C out/source/linux-6.18.60 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=/port/variants/emmc/out/kernel olddefconfig
      make -C out/source/linux-6.18.60 -j"$FIREFLY_EMMC_JOBS" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=/port/variants/emmc/out/kernel rockchip/rk3288-firefly-android17-emmc.dtb
      cd out/source/u-boot-2024.01
      make CROSS_COMPILE=arm-linux-gnueabihf- O=/port/variants/emmc/out/uboot firefly-rk3288_defconfig
      scripts/config --file /port/variants/emmc/out/uboot/.config \
        --disable ENV_IS_IN_MMC --enable ENV_IS_NOWHERE \
        --disable SILENT_CONSOLE --enable BOOTSTD_FULL --enable CMD_SYSBOOT \
        --enable MISC --enable ROCKCHIP_EFUSE --enable MISC_INIT_R \
        --enable HASH --enable SHA256 --disable CMD_FUSE \
        --disable MMC_HS200_SUPPORT --disable MMC_HS400_SUPPORT \
        --set-val BOOTDELAY 5 \
        --set-str LOCALVERSION "-firefly-android-emmc1"
      python3 /port/variants/emmc/scripts/set-bootcommand.py /port/variants/emmc/out/uboot/.config
      make CROSS_COMPILE=arm-linux-gnueabihf- O=/port/variants/emmc/out/uboot olddefconfig
      make -j"$FIREFLY_EMMC_JOBS" CROSS_COMPILE=arm-linux-gnueabihf- O=/port/variants/emmc/out/uboot
    ' 2>&1 | tee "$variant_root/records/build.log"
cp "$variant_root/out/uboot/.config" "$variant_root/configs/uboot.config"
cp "$variant_root/out/kernel/.config" "$variant_root/configs/kernel.config"
dtc -I dts -O dtb -b 0 -o "$variant_root/boot/rk3288-firefly-android.dtb" "$port_root/kernel/final/device-tree/rk3288-firefly-es8323-npll216.decompiled.dts"
printf '%s  %s\n' 2021fedaf9241b18d8184191c24a740f05beaceac0aeffb80c41376e1c815c5b "$variant_root/boot/rk3288-firefly-android.dtb" | sha256sum -c -
install -m 644 "$variant_root/out/uboot/idbloader.img" "$variant_root/bootloader/idbloader.img"
install -m 644 "$variant_root/out/uboot/u-boot-dtb.img" "$variant_root/bootloader/u-boot-dtb.img"
python3 "$variant_root/tests/test-identity-init.py" --image "$build_image"
docker image inspect --format '{{.Id}}' "$build_image" > "$variant_root/records/builder-image-id.txt"
docker run --rm --user "$(id -u):$(id -g)" -v "$port_root:/port" -w /port/variants/emmc "$build_image" python3 tests/check-media-contract.py
docker run --rm --user "$(id -u):$(id -g)" -v "$port_root:/port" -w /port/variants/emmc "$build_image" python3 scripts/record-build.py --image "$build_image" --jobs "$build_jobs"
(cd "$variant_root" && sha256sum boot/rk3288-firefly-android.dtb boot/extlinux.conf bootloader/idbloader.img bootloader/u-boot-dtb.img > SHA256SUMS)
echo 'Built and inspected the independent eMMC boot assets.'
