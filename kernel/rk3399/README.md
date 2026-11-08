# Original Firefly-RK3399 ARM64 kernel

`build-kernel.sh` builds Linux 6.18.60 from the SHA256-pinned upstream archive,
ARM64 defconfig, and `android.config`. It does not apply RK3288 kernel patches.
Pass the archive, a new output directory, and an optional job count:

```sh
bash build-kernel.sh /cache/linux-6.18.60.tar.xz /work/rk3399-kernel 4
```

Required tools include GCC/binutils for `aarch64-linux-gnu`, GNU make, Python 3,
dtc/fdtget, flex, bison, bc, OpenSSL headers and libelf headers. The output is an
uncompressed ARM64 `Image`, board DTB, and matching Wi-Fi modules. The validator
checks the ARM64 header, board compatibility, build configuration, DTB sound/USB
properties, module ELF architecture, vermagic and imported symbol CRCs.

The DTS includes the original upstream `rk3399-firefly.dts`. Its only changes are
stable sound card names (`FireflyRT5640`, `FireflyHDMI`), the headphone DAPM pin
switch, enabling HDMI audio, and dedicating USB-C to a USB2 peripheral for ADB.
It keeps upstream CPU, regulator, SDIO, memory and power-domain definitions.

Board-dependent boot drivers are built into the kernel, including eMMC/SD,
Ethernet, USB-C FUSB302/TCPM, thermal, I2S and RT5640 audio. Wi-Fi is staged as
six modules compiled against this exact kernel; do not substitute modules from
another build. Firmware is fetched through the separate AP6356S manifest.
`select-modules.py` removes optional defconfig module selections that the product
does not ship. The configuration gate checks the original board's PMIC,
regulators, clocks, GPIO, storage, Ethernet, USB/Type-C, PHYs, IOMMU, display,
audio, SARADC, PCIe and sensor drivers remain built in before compilation.

The original DTS does not fully connect TCPM data-role changes to DWC3 and its
SuperSpeed PHY. The first candidate therefore sets USB0 to `peripheral`, limits
it to `high-speed`, and uses only `u2phy0_otg`. The Type-C connector advertises a
device data role while preserving the upstream dual power role and try-sink
policy. Other USB host ports are unchanged. USB-C host use, SuperSpeed and
DisplayPort are not enabled by this ADB profile. A-C/C-C cable enumeration and
both plug orientations still require hardware testing.

Mainline rkvdec supports H.264 and VP9 on RK3399. This candidate does not claim
HEVC decoding or any tested 4K playback rate. Successful compilation and static
validation are not a real-board boot, Wi-Fi, sound or hardware decoding test.
