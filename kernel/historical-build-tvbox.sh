#!/usr/bin/env bash
echo "Historical source only. Use kernel/final/build-kernel.sh." >&2
exit 2
# SPDX-License-Identifier: MIT
set -euo pipefail
kernel_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
port_root=$(cd -- "$kernel_root/.." && pwd)
archive_root=$(cd -- "$port_root/.." && pwd)
kernel_work=${FIREFLY_TVBOX_KERNEL_WORK:-$archive_root/tvbox-work/kernel}
kernel_image=${FIREFLY_BUILD_IMAGE:-firefly-batocera-build:20261102}
kernel_jobs=${FIREFLY_KERNEL_JOBS:-2}
[[ "$kernel_jobs" =~ ^[12]$ ]] || { echo 'FIREFLY_KERNEL_JOBS must be 1 or 2' >&2; exit 2; }
docker image inspect "$kernel_image" >/dev/null
mkdir -p "$kernel_work" "$port_root/records/kernel-tvbox"
(cd "$kernel_root/downloads" && sha256sum -c source.sha256)
if [[ ! -d "$kernel_work/linux-6.18.60" ]]; then
    tar -xJf "$kernel_root/downloads/linux-6.18.60.tar.xz" -C "$kernel_work"
fi
kernel_source=$kernel_work/linux-6.18.60
cp "$kernel_root/hevc/rkvdec-hevc.c" "$kernel_source/drivers/media/platform/rockchip/rkvdec/"
if ! rg -q 'rk3288_hevc_variant' "$kernel_source/drivers/media/platform/rockchip/rkvdec/rkvdec.c"; then
    patch --batch --forward -d "$kernel_source" -p1 < "$kernel_root/hevc/linux-6.18-rk3288-hevc.patch"
fi
cp "$kernel_root/"rk3288-firefly-tvbox{,-emmc}.dts "$kernel_source/arch/arm/boot/dts/rockchip/"
cp "$kernel_root/rc-firefly-rk3288.c" "$kernel_source/drivers/media/rc/keymaps/"
if ! rg -q '^dtb-\$\(CONFIG_ARCH_ROCKCHIP\) \+= rk3288-firefly-tvbox.dtb$' "$kernel_source/arch/arm/boot/dts/rockchip/Makefile"; then
    printf '%s\n' 'dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3288-firefly-tvbox.dtb' >> "$kernel_source/arch/arm/boot/dts/rockchip/Makefile"
fi
if ! rg -q '^dtb-\$\(CONFIG_ARCH_ROCKCHIP\) \+= rk3288-firefly-tvbox-emmc.dtb$' "$kernel_source/arch/arm/boot/dts/rockchip/Makefile"; then
    printf '%s\n' 'dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3288-firefly-tvbox-emmc.dtb' >> "$kernel_source/arch/arm/boot/dts/rockchip/Makefile"
fi
if ! rg -q '^obj-\$\(CONFIG_RC_MAP\) \+= rc-firefly-rk3288.o$' "$kernel_source/drivers/media/rc/keymaps/Makefile"; then
    printf '%s\n' 'obj-$(CONFIG_RC_MAP) += rc-firefly-rk3288.o' >> "$kernel_source/drivers/media/rc/keymaps/Makefile"
fi
cp "$kernel_root/firefly-tvbox.config" "$kernel_work/firefly-tvbox.config"
cp "$kernel_root/scripts/check-binder-abi.c" "$kernel_work/check-binder-abi.c"
docker run --rm --init --user "$(id -u):$(id -g)" --cpus=2 \
    -e KBUILD_BUILD_TIMESTAMP='2026-11-04 00:00:00 UTC' \
    -e KBUILD_BUILD_USER=firefly -e KBUILD_BUILD_HOST=builder -e KBUILD_BUILD_VERSION=1 \
    -e FIREFLY_KERNEL_JOBS="$kernel_jobs" \
    -v "$kernel_work:/kernel" -w /kernel/linux-6.18.60 "$kernel_image" bash -c '
      set -euo pipefail
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build multi_v7_defconfig
      ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- scripts/kconfig/merge_config.sh -m -O ../build ../build/.config ../firefly-tvbox.config
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build olddefconfig
      make -j"$FIREFLY_KERNEL_JOBS" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build zImage rockchip/rk3288-firefly-tvbox.dtb rockchip/rk3288-firefly-tvbox-emmc.dtb
      arm-linux-gnueabihf-gcc -D__EXPORTED_HEADERS__ -Wall -Werror -c /kernel/check-binder-abi.c -Iinclude/uapi -Iarch/arm/include/uapi -I../build/arch/arm/include/generated/uapi -I../build/include/generated/uapi -o /kernel/binder64-abi-check.o
    ' > "$kernel_work/build.log" 2>&1
python3 "$kernel_root/scripts/audit-tvbox-kernel.py" --root "$kernel_work" --output "$port_root/records/kernel-tvbox/audit.json"
cp "$kernel_work/build/.config" "$port_root/records/kernel-tvbox/config-6.18.60-firefly-tvbox"
cp "$kernel_work/build/arch/arm/boot/zImage" "$port_root/device/firefly/rk3288/prebuilts/zImage"
cp "$kernel_work/build/arch/arm/boot/dts/rockchip/rk3288-firefly-tvbox.dtb" "$port_root/device/firefly/rk3288/prebuilts/rk3288-firefly-android.dtb"
cp "$kernel_work/build/arch/arm/boot/dts/rockchip/rk3288-firefly-tvbox-emmc.dtb" "$port_root/variants/emmc/boot/rk3288-firefly-android.dtb"
echo "TV kernel, TF DTB and eMMC DTB installed in $port_root"
