# Kernel authority

Use `final/build-kernel.sh` and the complete cumulative patch/configuration in
`final/`. These contain all 34 changed source files against Linux 6.18.60,
including the Hantro DMA-address-zero fix. Do not apply the small DMA patch
again on top. The final standalone decompiled DTS keeps custom HEVC and its
MMU disabled, and uses NPLL 216 MHz for the tested 1600x900 monitor.

The other configurations, HEVC implementation and historical build scripts in
this directory document earlier bring-up. They are not the final bootable
configuration. In particular, enabling the experimental HEVC nodes can hang
startup. The final export retained diagnostics that were in the tested kernel.

The export's patch replay and source hashes were checked. A clean kernel and
whole-product rebuild have not been repeated for this public integration.
