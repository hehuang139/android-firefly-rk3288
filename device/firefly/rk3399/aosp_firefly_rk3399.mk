# SPDX-License-Identifier: Apache-2.0
# Original Firefly-RK3399, ARM64 with ARM32 application compatibility, remote-first television product.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
PRODUCT_IS_ATV := true
PRODUCT_SUPPORTS_CAMERA := false
PRODUCT_SUPPORTS_TUNER := false
$(call inherit-product, device/google/atv/products/atv_system.mk)
$(call inherit-product, device/google/atv/products/atv_system_ext.mk)
$(call inherit-product, device/google/atv/products/atv_product.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/media_vendor.mk)
$(call inherit-product, device/firefly/rk3399/device.mk)

PRODUCT_NAME := aosp_firefly_rk3399
PRODUCT_DEVICE := rk3399
PRODUCT_BRAND := Firefly
PRODUCT_MODEL := Firefly-RK3399 TV
PRODUCT_MANUFACTURER := Firefly
PRODUCT_CHARACTERISTICS := tv
PRODUCT_LOCALES := zh_CN en_US
