# Original Firefly-RK3399 AP6356S Wi-Fi candidate

The upstream original-board DTS names AP6356S. Its BCM4356 SDIO function uses
vendor/device `02d0:4356` on controller `fe310000.mmc`, WL_REG_ON at GPIO0_B2,
and the RK808 32 kHz clock. This port uses that upstream wiring unchanged.
No RK3288 SDIO reset/rebind workaround is applied.

`fetch-firmware.py` retrieves SHA256-pinned Ubuntu linux-firmware and wireless-regdb
packages, verifies them and the selected payloads, and extracts only the requested
firmware, upstream AP6356S NVRAM template and licenses. It accepts an existing
verified package cache. The board template is not a device backup and contains no
user Wi-Fi credentials. It includes the upstream template's placeholder MAC,
not a measured per-device identity. Verify that the runtime interface uses the
board's unique address before deploying multiple units. Do not replace it with
an unrelated board's calibration.

```sh
python3 fetch-firmware.py --cache /cache/firmware \
  --output prebuilts/firmware
```

Stage `cfg80211`, `brcmutil`, `brcmfmac`, `brcmfmac-wcc`, `brcmfmac-cyw` and
`brcmfmac-bca` modules from this exact ARM64 kernel build in `prebuilts/modules`.
The kernel validator checks vermagic, imported symbol CRCs and dependency closure.
The init helper requires the exact kernel release and waits for both SDIO
functions, loads all firmware-vendor modules with autoprobing temporarily paused,
then restores the prior setting and probes the device. Missing hardware causes a
logged failure; it does not trigger controller resets.

The product uses the AOSP NL80211 supplicant path and the station-only Wi-Fi HAL
configuration declared in `BoardConfigWifi.mk`. Scanning, association, regulatory
operation, suspend/resume and throughput still require testing on the target
RK3399 board. Extracting firmware and compiling modules do not establish that
those runtime functions work.
