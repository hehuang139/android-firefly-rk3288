#!/bin/sh
# Reconstruct the complete tested source baseline without modifying an existing tree.
set -eu
package_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
archive=${1:?Usage: build-kernel.sh linux-6.18.60.tar.xz NEW_BUILD_DIRECTORY [JOBS]}
build_root=${2:?A new output directory is required}
jobs=${3:-8}
archive=$(realpath -- "$archive")
printf '%s  %s\n' '3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e' "$archive" | sha256sum -c -
test ! -e "$build_root" || { echo 'Output path already exists; refusing overwrite.' >&2; exit 1; }
mkdir -p -- "$build_root"
build_root=$(realpath -- "$build_root")
tar -xJf "$archive" -C "$build_root"
src_dir="$build_root/linux-6.18.60"
out_dir="$build_root/build"
cd "$src_dir"
git apply --check "$package_dir/linux-6.18.60-firefly-final.patch"
git apply "$package_dir/linux-6.18.60-firefly-final.patch"
mkdir "$out_dir"
cp "$package_dir/firefly-rk3288-final.config" "$out_dir/.config"
export KBUILD_BUILD_TIMESTAMP='2026-11-04 00:00:00 UTC'
export KBUILD_BUILD_USER=firefly
export KBUILD_BUILD_HOST=builder
export KBUILD_BUILD_VERSION=1
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O="$out_dir" olddefconfig
cmp "$package_dir/firefly-rk3288-final.config" "$out_dir/.config"
make -j"$jobs" ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- O="$out_dir" zImage modules
dtc -I dts -O dtb -b 0 -o "$build_root/rk3288-firefly-es8323-npll216.dtb" "$package_dir/device-tree/rk3288-firefly-es8323-npll216.decompiled.dts"
printf '%s  %s\n' '2021fedaf9241b18d8184191c24a740f05beaceac0aeffb80c41376e1c815c5b' "$build_root/rk3288-firefly-es8323-npll216.dtb" | sha256sum -c -
python3 "$package_dir/../../scripts/prepare-wifi-kernel.py" \
    --kernel-build "$out_dir" --output "$build_root/wifi"
sha256sum "$out_dir/arch/arm/boot/zImage" "$out_dir/.config"
echo 'Build completed. No board was written. Compare zImage with the recorded tested hash; see README for reproducibility limits.'
