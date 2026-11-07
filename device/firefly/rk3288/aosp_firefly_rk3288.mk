# SPDX-License-Identifier: Apache-2.0
# Original Firefly-RK3288, 2 GiB RAM, remote-first television product.
PRODUCT_IS_ATV := true
PRODUCT_SUPPORTS_CAMERA := false
PRODUCT_SUPPORTS_TUNER := false
$(call inherit-product, device/google/atv/products/atv_system.mk)
$(call inherit-product, device/google/atv/products/atv_system_ext.mk)
$(call inherit-product, device/google/atv/products/atv_product.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/media_vendor.mk)
$(call inherit-product, device/google/atv/products/atv_lowram_defaults.mk)
$(call inherit-product, device/firefly/rk3288/device.mk)

PRODUCT_NAME := aosp_firefly_rk3288
PRODUCT_DEVICE := rk3288
PRODUCT_BRAND := Firefly
PRODUCT_MODEL := Firefly-RK3288 TV
PRODUCT_MANUFACTURER := Firefly
PRODUCT_CHARACTERISTICS := tv
PRODUCT_LOCALES := zh_CN en_US
