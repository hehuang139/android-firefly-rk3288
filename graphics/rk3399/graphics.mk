# SPDX-License-Identifier: Apache-2.0
PRODUCT_ALLOWED_ANDROIDMK_FILES += device/firefly/rk3399/graphics/aospext/Android.mk
PRODUCT_PACKAGES += \
    libEGL_mesa \
    libGLESv1_CM_mesa \
    libGLESv2_mesa \
    libgallium_dri \
    android.hardware.graphics.allocator-service.minigbm \
    mapper.minigbm \
    android.hardware.composer.hwc3-service.drm

PRODUCT_VENDOR_PROPERTIES += \
    ro.hardware.egl=mesa \
    ro.hardware.gralloc=minigbm \
    ro.hardware.hwcomposer=drm \
    ro.opengles.version=196609 \
    ro.gfx.angle.supported=false \
    debug.hwui.renderer=skiagl \
    debug.sf.disable_hwc_vds=1 \
    vendor.hwc.backend_override=client \
    ro.vendor.hwc.use_overlay_planes=0

# ClientBackend flattens every layer, including cursors, into the GPU client
# target. Keep the first HDMI boot on one primary scanout plane.

# AOSP's alloc/mapper/composer packages provide their VINTF fragments.
# Do not duplicate graphics HALs in the board's standalone manifest.xml.
