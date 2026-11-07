# Android TF-card loaders for original Firefly-RK3288

This directory contains an independently rebuilt U-Boot v2024.01 for the
original `firefly-rk3288_defconfig`. SD is `mmc1`; the boot command is
`setenv boot_targets mmc1; bootflow scan -lb`. Environment changes exist only in
RAM (`CONFIG_ENV_IS_NOWHERE=y`); this build does not save environment to eMMC.
The image loads zImage, the Android gzip init ramdisk, and the board DTB through
FAT/extlinux and `bootz`; Android boot.img parsing is not required.

- `idbloader.img`: byte offset 32768.
- `u-boot-dtb.img`: byte offset 8388608.
- First partition: FAT32 at byte offset 16777216.
- GPT primary entries finish before the IDB loader; backup GPT is at image end.
- `SHA256SUMS` and `source/uboot-manifest.json` describe these actual binaries.

## Per-board identity

`source/patches/0001-firefly-nonfatal-efuse-identity.patch` provides a strong
board-specific `misc_init_r`. After relocation, it reads the 16-byte RK3288 CPU
ID at eFuse byte offset 7 through U-Boot's read-only `misc_read` driver. The
Rockchip eFuse driver only has a read operation, and `CONFIG_CMD_FUSE` is disabled.
This does not program or burn any fuse.

The upstream Rockchip helpers derive a stable `serial#` with CRC32 mixing and
a local, unicast `ethaddr` with SHA256 of the hexadecimal CPU ID. A pre-existing
valid environment Ethernet address is preserved. `serial#` is available for
extlinux's `androidboot.serialno=${serial#}`. The normal U-Boot FDT boot fixups
also set the root `serial-number` and Ethernet `local-mac-address`, using the
kernel DTB's `ethernet0` alias. The Android kernel DTB currently maps this alias
to `/ethernet@ff290000`.

An eFuse read error, all-zero/all-FF CPU ID, serial setup error, or MAC setup
error emits a warning and **returns success to the boot sequence**. There is no
fixed shared serial fallback. If identity cannot be obtained, the serial can
remain unset and the existing U-Boot random-MAC fallback remains available.

`0002-rockchip-efuse-main-uboot-only.patch` limits the eFuse driver to the main
U-Boot stage. TPL uses OF_PLATDATA and cannot link the driver's address accessor;
identity initialization is not needed during DDR/TPL or SPL startup.

## Rebuild

The complete original source archive is stored in `source/`, with SHA256:
`a03c3c2ba9d2bea5176c6406f1f3429a79e1147be242f5a07dbd9e89b3cc83c4`.
The script checks the archive, applies the two patches idempotently, compiles,
runs identity fault-injection tests, validates ARM symbols and image CRCs, and
updates the binaries/configuration/manifest/checksums in this directory.

```sh
docker build -t firefly-rk3288-uboot-builder:local source
FIREFLY_UBOOT_BUILD_IMAGE=firefly-rk3288-uboot-builder:local \
  ./source/rebuild-u-boot.sh
```

The recorded build used the existing local
`firefly-batocera-build:20261102` compiler container, with GCC 11.4.0. Its exact
image ID and the applied patch/configuration hashes are in
`source/uboot-manifest.json`. The rebuild script and standalone identity test
now default to `firefly-rk3288-uboot-builder:local`, built by the command above;
the rebuild passes its selected image to the test. `SOURCE_DATE_EPOCH` is fixed to
1704672000. No host block device is opened by the build script.

Actual checks are saved in `source/identity-init-validation.json`,
`source/identity-symbols.txt`, and `source/build.log`. The host test compiles the
actual patched board function and upstream serial/MAC functions, injecting
read errors and invalid IDs through mocks; it does not access hardware.
Both the legacy U-Boot image header CRC and its payload CRC were verified.
The initial TPL link failure and subsequent fix are retained in
`source/build-attempt-01.log`.

U-Boot and the board patches retain GPL-2.0-or-later licensing. Build and
verification scripts are MIT. Redistribute the upstream archive, patches, build
configuration and scripts together with these loader binaries.
