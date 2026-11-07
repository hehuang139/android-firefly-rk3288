#!/usr/bin/env bash
echo "Historical source only. Use kernel/final/build-kernel.sh." >&2
exit 2
# SPDX-License-Identifier: MIT
set -euo pipefail
# Independent full kernel build; does not install into AOSP or prebuilts.
kernel_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
port_root=$(cd -- "$kernel_root/.." && pwd)
work_root=$(cd -- "$port_root/.." && pwd)
kernel_work=${FIREFLY_REBOOT_KERNEL_WORK:-$work_root/kernel-reboot-mode-work}
kernel_image=${FIREFLY_BUILD_IMAGE:-firefly-android17-kernel:local}
kernel_jobs=${FIREFLY_KERNEL_JOBS:-2}
[[ "$kernel_jobs" =~ ^[12]$ ]] || { echo 'FIREFLY_KERNEL_JOBS must be 1 or 2' >&2; exit 2; }
docker image inspect "$kernel_image" >/dev/null
kernel_cpu_set=$(python3 -c 'import os; print(",".join(map(str, sorted(os.sched_getaffinity(0))[-2:])))')
mkdir -p "$kernel_work" "$port_root/records/kernel-reboot-mode"
(cd "$kernel_root/downloads" && sha256sum -c source.sha256)
if [[ ! -d "$kernel_work/linux-6.18.60" ]]; then
    tar -xJf "$kernel_root/downloads/linux-6.18.60.tar.xz" -C "$kernel_work"
fi
cp "$kernel_root/rk3288-firefly-android17.dts" "$kernel_work/linux-6.18.60/arch/arm/boot/dts/rockchip/"
if ! rg -q '^dtb-\$\(CONFIG_ARCH_ROCKCHIP\) \+= rk3288-firefly-android17.dtb$' "$kernel_work/linux-6.18.60/arch/arm/boot/dts/rockchip/Makefile"; then
    printf '%s\n' 'dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3288-firefly-android17.dtb' >> "$kernel_work/linux-6.18.60/arch/arm/boot/dts/rockchip/Makefile"
fi
cp "$kernel_root/firefly-android17.config" "$kernel_work/firefly-android17.config"
cp "$kernel_root/scripts/check-binder-abi.c" "$kernel_work/check-binder-abi.c"
docker run --rm --init --user "$(id -u):$(id -g)" --cpus=2 --cpuset-cpus="$kernel_cpu_set" \
    -e KBUILD_BUILD_TIMESTAMP='2026-10-30 00:00:00 UTC' \
    -e KBUILD_BUILD_USER=firefly -e KBUILD_BUILD_HOST=builder -e KBUILD_BUILD_VERSION=1 \
    -e FIREFLY_KERNEL_JOBS="$kernel_jobs" \
    -v "$kernel_work:/kernel" -w /kernel/linux-6.18.60 "$kernel_image" bash -c '
      set -euo pipefail
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build multi_v7_defconfig
      ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- scripts/kconfig/merge_config.sh -m -O ../build ../build/.config ../firefly-android17.config
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build olddefconfig
      make -j"$FIREFLY_KERNEL_JOBS" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build zImage modules rockchip/rk3288-firefly-android17.dtb
      make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O=../build INSTALL_MOD_PATH=/kernel/staging INSTALL_MOD_STRIP=1 DEPMOD=true modules_install
      arm-linux-gnueabihf-gcc -D__EXPORTED_HEADERS__ -Wall -Werror -c /kernel/check-binder-abi.c -Iinclude/uapi -Iarch/arm/include/uapi -I../build/arch/arm/include/generated/uapi -I../build/include/generated/uapi -o /kernel/binder64-abi-check.o
    ' > "$kernel_work/build.log" 2>&1
for link in "$kernel_work/staging/lib/modules/6.18.60-firefly-android17/build" "$kernel_work/staging/lib/modules/6.18.60-firefly-android17/source"; do
    [[ ! -L "$link" ]] || rm -- "$link"
done
depmod -b "$kernel_work/staging" -F "$kernel_work/build/System.map" 6.18.60-firefly-android17
python3 "$kernel_root/scripts/audit-kernel.py" --root "$kernel_work"
cp "$kernel_work/build/.config" "$port_root/records/kernel-reboot-mode/config-6.18.60-firefly-android17"
cp "$kernel_work/kernel-audit.json" "$port_root/records/kernel-reboot-mode/kernel-audit.json"
python3 "$kernel_root/scripts/record-reboot-build.py" --work "$kernel_work" --image "$kernel_image"
echo "Independent kernel and modules: $kernel_work"
