// SPDX-License-Identifier: Apache-2.0
#include "cros_gralloc/cros_gralloc_driver.h"
#include "cros_gralloc/cros_gralloc_helpers.h"
#include <cstdio>
#include <cstdlib>
#include <inttypes.h>

int main(int argc, char **argv) {
    cros_gralloc_buffer_descriptor d{};
    d.width = 1920;
    d.height = 1080;
    d.droid_format = HAL_PIXEL_FORMAT_YCbCr_420_888;
    d.droid_usage = argc > 1 ? strtoull(argv[1], nullptr, 0) : 0x400933;
    d.drm_format = cros_gralloc_convert_format(d.droid_format);
    d.use_flags = cros_gralloc_convert_usage(d.droid_usage);
    d.enable_metadata_fd = true;
    d.name = "firefly-independent-nv12-preflight";
    printf("width=%u height=%u format=%d usage=0x%" PRIx64 " drm=0x%x use_flags=0x%" PRIx64 "\n",
           d.width, d.height, d.droid_format, uint64_t(d.droid_usage), d.drm_format, d.use_flags);
    auto driver = cros_gralloc_driver::get_instance();
    if (!driver) { puts("driver=null"); return 2; }
    bool supported = driver->is_supported(&d);
    printf("supported=%d\n", supported);
    native_handle_t *handle = nullptr;
    int result = driver->allocate(&d, &handle);
    printf("allocate=%d handle=%p\n", result, static_cast<void *>(handle));
    if (result || !handle) return 1;
    auto h = cros_gralloc_convert_handle(handle);
    printf("resolved_format=0x%x resolved_use_flags=0x%" PRIx64 " planes=%u pixel_stride=%u size=%" PRIu64 "\n",
           h->format, h->use_flags, h->num_planes, h->pixel_stride, uint64_t(h->total_size));
    for (uint32_t i = 0; i < h->num_planes; ++i)
        printf("plane=%u fd=%d stride=%u offset=%u size=%u\n", i, h->fds[i], h->strides[i], h->offsets[i], h->sizes[i]);
    int released = driver->release(handle);
    printf("release=%d\n", released);
    native_handle_close(handle);
    native_handle_delete(handle);
    return released ? 3 : 0;
}
