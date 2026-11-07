# Original Firefly-RK3288 eMMC assets

Build from the repository root using the [current build guide](../../BUILD.md).
`rebuild.sh` fetches pinned U-Boot v2024.01, applies the three local patches,
builds the same eMMC boot command/configuration and compiles the final
standalone DTS. It does not require earlier TF binaries or private records.
It runs the identity failure-injection test and emits checksums, but does not
claim a fresh board boot test or full Android image validation.

The final configuration uses 8-bit 50 MHz SDR eMMC at ff0f0000, disables the
TF controller in the eMMC device tree, keeps U-Boot environment only in RAM,
and boots `/extlinux/extlinux.conf` from eMMC partition 1. The shipped extlinux
matches the tested boot arguments after removing unused trailing padding;
there is no single-CPU switch or Hantro blocklist. `loglevel=0` suppresses
ordinary kernel messages. Changing it to 7 enables debugging, not a fix.

`historical-rebuild.sh`, old kernel.config/DTS and record scripts are retained
as non-default bring-up references. The authoritative kernel/config/DT source
is kernel/final. Raw assembled images occupy 12 GiB and need a suitable eMMC.
