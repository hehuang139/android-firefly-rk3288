#!/usr/bin/env bash
echo "Historical source only. Use kernel/final/build-kernel.sh." >&2
exit 2
# SPDX-License-Identifier: MIT
set -euo pipefail
KERNEL_TASK_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
KERNEL_BUILD_IMAGE=${FIREFLY_BUILD_IMAGE:-firefly-android17-kernel:local}
KERNEL_VERSION=6.18.60
KERNEL_SRC="$KERNEL_TASK_DIR/linux-$KERNEL_VERSION"
(cd "$KERNEL_TASK_DIR/downloads" && sha256sum -c source.sha256)
if [[ ! -d "$KERNEL_SRC" ]]; then
    tar -xJf "$KERNEL_TASK_DIR/downloads/linux-$KERNEL_VERSION.tar.xz" -C "$KERNEL_TASK_DIR"
fi
cp "$KERNEL_TASK_DIR/rk3288-firefly-android17.dts" "$KERNEL_SRC/arch/arm/boot/dts/rockchip/"
if ! rg -q '^dtb-\$\(CONFIG_ARCH_ROCKCHIP\) \+= rk3288-firefly-android17.dtb$' "$KERNEL_SRC/arch/arm/boot/dts/rockchip/Makefile"; then
    printf '%s\n' 'dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3288-firefly-android17.dtb' >> "$KERNEL_SRC/arch/arm/boot/dts/rockchip/Makefile"
fi
docker run --rm --label firefly.android17.kernel=1 --user "$(id -u):$(id -g)" \
    -e KBUILD_BUILD_TIMESTAMP='2026-10-30 00:00:00 UTC' \
    -e KBUILD_BUILD_USER=firefly -e KBUILD_BUILD_HOST=builder \
    -e KBUILD_BUILD_VERSION=1 \
    -v "$KERNEL_TASK_DIR:/kernel" -w "/kernel/linux-$KERNEL_VERSION" \
    "$KERNEL_BUILD_IMAGE" bash -c '
      set -euo pipefail
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build multi_v7_defconfig
      ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- scripts/kconfig/merge_config.sh -m -O ../build ../build/.config ../firefly-android17.config
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build olddefconfig
      make -j12 ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build zImage modules rockchip/rk3288-firefly-android17.dtb
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build INSTALL_MOD_PATH=/kernel/staging INSTALL_MOD_STRIP=1 DEPMOD=true modules_install
      arm-linux-gnueabihf-gcc -D__EXPORTED_HEADERS__ -Wall -Werror -c /kernel/scripts/check-binder-abi.c -Iinclude/uapi -Iarch/arm/include/uapi -I../build/arch/arm/include/generated/uapi -I../build/include/generated/uapi -o /kernel/binder64-abi-check.o
    '
for KERNEL_LINK in "$KERNEL_TASK_DIR/staging/lib/modules/$KERNEL_VERSION-firefly-android17/build" "$KERNEL_TASK_DIR/staging/lib/modules/$KERNEL_VERSION-firefly-android17/source"; do
    if [[ -L "$KERNEL_LINK" ]]; then
        rm -- "$KERNEL_LINK"
    fi
done
depmod -b "$KERNEL_TASK_DIR/staging" -F "$KERNEL_TASK_DIR/build/System.map" "$KERNEL_VERSION-firefly-android17"
cp "$KERNEL_TASK_DIR/build/.config" "$KERNEL_TASK_DIR/config-$KERNEL_VERSION-firefly-android17"
