# Native video probes

- `firefly_hwdecode.c` is the original Apache-2.0 V4L2 Request pixel probe.
  It verifies the hardware frame context and hashes visible NV12 pixels.
  Build it through the complete device media `Android.bp` and its pinned
  FFmpeg headers/libraries. Per-frame transfer and hashing make elapsed time
  unsuitable as a realtime Surface playback benchmark.
- `allocator-probe.cc` calls the cros_gralloc C++ driver with an exact
  1920x1080 flexible-YUV Surface descriptor. It depends on the pinned
  minigbm internal headers, libminigbm_gralloc, libdrm and Android headers.
  It allocates and releases test buffers; it is not a passive observation.
- `drm-vblank-probe.cc` uses libdrm/libdrmMode and opens card0 read-only to
  enumerate modes/planes and observe vblank. Device access permissions are
  required. It does not set modes, claim/drop master or write registers.

These two small C++ probes have newly assigned Apache-2.0 SPDX headers.
Their third-party linked dependencies retain their own licenses. No private
cross-compiler paths or prebuilt executables are included. To make these
reproducible product modules, add cc_binary definitions to the pinned full
device tree and validate the resulting binaries before suggesting a reader
deploy them.
