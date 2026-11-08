# Original Firefly-RK3399 eMMC boot profile

This candidate uses a FAT boot partition containing `extlinux/extlinux.conf`,
`boot/Image`, `boot/ramdisk.img`, and `boot/rk3399-firefly-android.dtb`.
The ramdisk is the gzip-compressed AOSP ARM64 first-stage ramdisk, not Android
`boot.img`. The kernel is an uncompressed ARM64 Image, not an ARM32 zImage.

The original board's mainline U-Boot aliases eMMC as `mmc0` and TF as `mmc1`.
Linux aliases differ: eMMC is `mmc2`, TF is `mmc1`, and SDIO is `mmc0`.
Android uses the controller identity `fe330000.mmc` to avoid numbering ambiguity.
The associated SPL and U-Boot candidate restrict their next stage to eMMC.
This does not change the SoC BootROM's hardware boot priority.

The UART2 console is 1500000 baud, 8N1. This development profile starts SELinux
permissively and reports unlocked/orange verified-boot state. It is not a
production security configuration. No real-board boot has been validated yet.
