# Original Firefly-RK3399 DDR3 bootloader

`build-bootloader.sh` builds upstream U-Boot v2024.01 and TF-A v2.10 from the
SHA256-pinned archives in `sources.json`. It uses the original board's DDR3-1600
TPL, SPL and a source-built BL31. It does not reuse the RK3288 binary loader.

```sh
bash build-bootloader.sh /cache/u-boot-v2024.01.tar.gz \
  /cache/arm-trusted-firmware-v2.10.tar.gz /work/rk3399-bootloader 4
```

The build needs `aarch64-linux-gnu` and `arm-linux-gnueabihf` cross tools, make,
Python 3, dtc/fdtget, flex, bison, swig and development headers required by U-Boot.
The M0 tool wrapper disables Ubuntu compiler PIE defaults for that freestanding
TF-A component. No TF-A source change is applied.

Three explicit source edits restrict SPL to `sdhci` (eMMC), restrict the U-Boot
boot targets to `mmc0`, and align `kernel_addr_r=0x02000000` with the modern
ARM64 Image header's zero load offset. `CONFIG_BOOTSTD_FULL` enables the explicit automatic boot
command `bootflow scan -lbG mmc0`: list flows, boot them, skip global methods,
and select eMMC. The environment is compiled in and is never saved to storage.
No video console is enabled. UART2 uses 1500000 baud, 8N1.

The image assembler places `idbloader.img` at byte 32768 (LBA 64) and
`u-boot.itb` at byte 8388608 (LBA 16384). Alternatively the combined
`u-boot-rockchip.bin` begins at byte 32768; it already contains the FIT at the
correct relative offset. These are disk boot assets, **not USB RAM Loaders**.

`validate-bootloader.py` checks board identity, aliases, SPL order, compiled
environment, TF-A architecture, FIT structure, combined-image placement and
artifact hashes. It writes `bootloader-manifest.json` only after all checks pass.
This is offline validation. No RK3399 boot or physical storage write is performed
by these scripts, and the BootROM's hardware boot priority is not changed.

## Separate USB RAM loader

`build-usb-loader.py /new/private/staging` fetches the separately licensed
Rockchip `rkbin` inputs pinned in `usb-loader-sources.json` and runs the official
Linux x86_64 `boot_merger`. The recipe is `RKBOOT/RK3399MINIALL.ini`, combining
RK3399 DDR 800 MHz v1.30, usbplug v1.30 and miniloader v1.30 into
`rk3399_loader_v1.30.130.bin`. The script verifies every input SHA256, retains
the Rockchip license, and records the output SHA256. Packed output metadata may
vary between packaging runs; use the generated manifest for the exact artifact.

This is the candidate for the Rockchip tool's **RAM Boot download** operation
when an RK3399 is in MaskROM. It is not a replacement for the source-built disk
TPL/SPL/U-Boot above. The package includes a FlashBoot component, so its presence
does not authorize a persistent loader update: select only the intended RAM
download operation. No target device is opened by this packaging script.
Real-board DDR initialization, eMMC access and readback remain untested. Never
substitute the RK3288 read-limit loader for this RK3399 candidate.
