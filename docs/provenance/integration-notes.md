# Public source integration changes

Scope: this is the historical RK3288 ARM32 export record. The RK3399 ARM64
installer intentionally excludes the ARM32 NetBpfLoad workaround; its current
build and validation status is recorded in [the RK3399 notes](../rk3399-port-status.md).

Historical exact inputs are recorded in the adjacent export manifests. This
public profile intentionally differs where listed below; those changes must
not be mistaken for byte-identical historical firmware reproduction.

- Complete kernel/final export replaces earlier default kernel scripts. Old
  entry points direct to final; historical scripts refuse accidental execution.
- Installer applies pinned cumulative minigbm and ARM32 NetBpfLoad patches with
  commit and before/after content-hash checks. The original install-port.py
  and device.mk did not contain the suspected split identifiers.
- U-Boot source/scripts/Dockerfiles/AIDL API hash and audio notice/config inputs
  omitted by the initial source filter were restored from original sources.
- Provider protocol/decryption implementations, station datasets and their
  catalog tools were omitted. The launcher compiles with direct URL playback
  and a fail-closed optional resolver stub; signed-provider refresh hooks were
  removed. Complete public launcher APK compilation/signature checks passed.
- Third-party APK preload list, channel list and programme guide are empty.
  EPG networking is disabled until explicitly configured. Missing optional
  kids media are not packaged and their launch buttons are hidden.
- Latest HDMI HAL/policy/monitor source is merged; software reboot and analog
  fallback tests passed. Physical HDMI audio/hotplug remain untested.
- Final extlinux arguments are retained; unused trailing padding is removed.
- Complete public Android/kernel clean rebuild is still pending. Historical
  media-specific aggregate validation cannot count as this release's pass.

No private SSH/serial tools, connection data, runtime account logs, APKs, images
or signing keys are part of this tree. Any binaries distributed separately
require a fresh corresponding-source and license audit.
