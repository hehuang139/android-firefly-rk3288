#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
# Builds ordinary files only; does not open any host block device.
TASK_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
IMAGE=${FIREFLY_UBOOT_BUILD_IMAGE:-firefly-rk3288-uboot-builder:local}
JOBS=${FIREFLY_UBOOT_JOBS:-8}
ARCHIVE="$TASK_DIR/u-boot-v2024.01.tar.gz"
SOURCE="$TASK_DIR/u-boot-2024.01"
if [[ ! -f "$ARCHIVE" ]]; then
  curl -fL --retry 3 'https://codeload.github.com/u-boot/u-boot/tar.gz/refs/tags/v2024.01' -o "$ARCHIVE"
fi
(cd "$TASK_DIR" && printf '%s  %s\n' 'a03c3c2ba9d2bea5176c6406f1f3429a79e1147be242f5a07dbd9e89b3cc83c4' 'u-boot-v2024.01.tar.gz' | sha256sum -c -)
if [[ ! -d "$SOURCE" ]]; then
  tar -xzf "$ARCHIVE" -C "$TASK_DIR"
fi
for change in "$TASK_DIR"/patches/*.patch; do
  if patch -d "$SOURCE" -p1 --forward --dry-run --batch < "$change" >/dev/null 2>&1; then
    patch -d "$SOURCE" -p1 --forward --batch < "$change"
  elif ! patch -d "$SOURCE" -p1 --reverse --dry-run --batch < "$change" >/dev/null 2>&1; then
    printf 'Patch does not match this source: %s\n' "$change" >&2
    exit 1
  fi
done

docker run --rm --user "$(id -u):$(id -g)" \
  -e SOURCE_DATE_EPOCH=1704672000 -e FIREFLY_UBOOT_JOBS="$JOBS" \
  -v "$TASK_DIR:/build" -w /build/u-boot-2024.01 "$IMAGE" \
  bash -c '
    set -euo pipefail
    make CROSS_COMPILE=arm-linux-gnueabihf- O=../build firefly-rk3288_defconfig
    scripts/config --file ../build/.config \
      --disable ENV_IS_IN_MMC --enable ENV_IS_NOWHERE \
      --disable SILENT_CONSOLE --enable BOOTSTD_FULL \
      --enable MISC --enable ROCKCHIP_EFUSE --enable MISC_INIT_R \
      --enable HASH --enable SHA256 --disable CMD_FUSE \
      --set-val BOOTDELAY 5 \
      --set-str BOOTCOMMAND "setenv boot_targets mmc1; bootflow scan -lb" \
      --set-str LOCALVERSION "-firefly-android-sd1"
    make CROSS_COMPILE=arm-linux-gnueabihf- O=../build olddefconfig
    make -j"$FIREFLY_UBOOT_JOBS" CROSS_COMPILE=arm-linux-gnueabihf- O=../build
  '
cp "$TASK_DIR/build/.config" "$TASK_DIR/uboot.config"
cp "$TASK_DIR/build/idbloader.img" "$TASK_DIR/../idbloader.img"
cp "$TASK_DIR/build/u-boot-dtb.img" "$TASK_DIR/../u-boot-dtb.img"
python3 "$TASK_DIR/tests/test-identity-init.py" --image "$IMAGE"
python3 "$TASK_DIR/record-build.py" --image "$IMAGE"
(cd "$TASK_DIR/.." && sha256sum idbloader.img u-boot-dtb.img > SHA256SUMS)
