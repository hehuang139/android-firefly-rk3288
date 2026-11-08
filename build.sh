#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
port_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_root=${FIREFLY_WORK_ROOT:-$(cd -- "$port_root/.." && pwd)}
work_root=$(realpath -- "$work_root")
action=${1:-help}
builder=${FIREFLY_ANDROID_BUILDER_IMAGE:-firefly-android17-builder:20261104}
jobs=${FIREFLY_ANDROID_JOBS:-12}

case "$action" in
  kernel)
    archive=${FIREFLY_KERNEL_ARCHIVE:?Set FIREFLY_KERNEL_ARCHIVE to the Linux 6.18.60 tar.xz}
    output=${FIREFLY_KERNEL_OUTPUT:-$work_root/kernel-release}
    sh "$port_root/kernel/final/build-kernel.sh" "$archive" "$output" "${FIREFLY_KERNEL_JOBS:-8}"
    mkdir -p "$port_root/device/firefly/rk3288/prebuilts" "$port_root/variants/emmc/boot"
    install -m 644 "$output/build/arch/arm/boot/zImage" "$port_root/device/firefly/rk3288/prebuilts/zImage"
    install -m 644 "$output/wifi/rk3288-firefly-wifi.dtb" "$port_root/variants/emmc/boot/rk3288-firefly-android.dtb"
    install -m 644 "$output/wifi/rk3288-firefly-wifi.dtb" "$port_root/device/firefly/rk3288/prebuilts/rk3288-firefly-android.dtb"
    mkdir -p "$port_root/device/firefly/rk3288/wifi/prebuilts/modules"
    for module in "$output"/wifi/modules/*.ko; do
      install -m 644 "$module" "$port_root/device/firefly/rk3288/wifi/prebuilts/modules/"
    done
    ;;
  install)
    python3 "$port_root/scripts/install-port.py" "$work_root/aosp"
    ;;
  lunch|graph|build|tools)
    build_cpu_set=$(python3 -c 'import os; print(",".join(map(str, sorted(os.sched_getaffinity(0))[:10])))')
    [[ -x "$work_root/tools/mesa-native/install/bin/mesa_clc" ]] || {
      echo 'Build the pinned native Mesa tools first' >&2; exit 1;
    }
    [[ -f "$work_root/aosp/device/firefly/rk3288/.firefly-port" ]] || {
      echo 'Run ./build.sh install first' >&2; exit 1;
    }
    docker run --rm --init --user "$(id -u):$(id -g)" \
      --memory=48g --memory-swap=48g --cpus=10 --cpuset-cpus="$build_cpu_set" \
      --volume "$work_root:$work_root" --workdir "$work_root/aosp" \
      "$builder" bash "$port_root/scripts/build-android-inside.sh" \
      "$work_root" "$action" "$jobs"
    ;;
  image|image-emmc)
    product_root="$work_root/aosp/out/target/product/rk3288"
    boot_root="$work_root/boot-files-tvbox"
    boot_medium=sd
    boot_assets="$port_root"
    dtb_source="$port_root/device/firefly/rk3288/prebuilts/rk3288-firefly-android.dtb"
    output_name=firefly-rk3288-tv-android17-sd-alpha.img
    if [[ "$action" == image-emmc ]]; then
      boot_medium=emmc
      boot_root="$work_root/boot-files-tvbox-emmc"
      boot_assets="$port_root/variants/emmc"
      dtb_source="$boot_assets/boot/rk3288-firefly-android.dtb"
      output_name=firefly-rk3288-tv-android17-emmc-alpha.img
    fi
    [[ -f "$product_root/ramdisk.img" ]] || {
      echo 'Build the Android product ramdisk before assembling the image' >&2; exit 1;
    }
    mkdir -p "$boot_root/boot" "$boot_root/extlinux"
    install -m 644 "$port_root/device/firefly/rk3288/prebuilts/zImage" "$boot_root/boot/zImage"
    install -m 644 "$dtb_source" "$boot_root/boot/rk3288-firefly-android.dtb"
    install -m 644 "$product_root/ramdisk.img" "$boot_root/boot/ramdisk.img"
    install -m 644 "$boot_assets/boot/extlinux.conf" "$boot_root/extlinux/extlinux.conf"
    docker run --rm --init --user "$(id -u):$(id -g)" \
      --volume "$work_root:$work_root" --workdir "$work_root" \
      "$builder" python3 "$port_root/scripts/assemble-sd.py" \
      --boot-medium "$boot_medium" \
      --product "$work_root/aosp/out/target/product/rk3288" \
      --boot-files "$boot_root" \
      --idbloader "$boot_assets/bootloader/idbloader.img" \
      --uboot "$boot_assets/bootloader/u-boot-dtb.img" \
      --simg2img "$work_root/aosp/out/host/linux-x86/bin/simg2img" \
      --output "$work_root/tvbox-artifacts/$output_name"
    ;;
  verify|verify-emmc)
    boot_medium=sd
    boot_root="$work_root/boot-files-tvbox"
    boot_assets="$port_root"
    image_name=firefly-rk3288-tv-android17-sd-alpha.img
    report_name=image-validation.json
    if [[ "$action" == verify-emmc ]]; then
      boot_medium=emmc
      boot_root="$work_root/boot-files-tvbox-emmc"
      boot_assets="$port_root/variants/emmc"
      image_name=firefly-rk3288-tv-android17-emmc-alpha.img
      report_name=emmc-image-validation.json
    fi
    docker run --rm --init --user "$(id -u):$(id -g)" \
      --volume "$work_root:$work_root" --workdir "$work_root" \
      "$builder" python3 "$port_root/scripts/verify-sd.py" \
      --boot-medium "$boot_medium" \
      --image "$work_root/tvbox-artifacts/$image_name" \
      --product "$work_root/aosp/out/target/product/rk3288" \
      --boot-files "$boot_root" \
      --idbloader "$boot_assets/bootloader/idbloader.img" \
      --uboot "$boot_assets/bootloader/u-boot-dtb.img" \
      --simg2img "$work_root/aosp/out/host/linux-x86/bin/simg2img" \
      --manifest "$work_root/tvbox-artifacts/$image_name.json" \
      --report "$work_root/tvbox-artifacts/$report_name"
    ;;
  help|-h|--help)
    echo 'Usage: ./build.sh {kernel|install|lunch|graph|build|tools|image|verify|image-emmc|verify-emmc}'
    echo 'Requires the synced android-17.0.0_r1 AOSP tree, native Mesa tools,'
    echo 'and the Android kernel prebuilts. Read docs/ before building.'
    ;;
  *) echo "Unknown action: $action" >&2; exit 2;;
esac
