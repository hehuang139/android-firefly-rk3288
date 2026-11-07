# SPDX-License-Identifier: Apache-2.0
FIREFLY_DEVICE_PATH := device/firefly/rk3288

PRODUCT_SHIPPING_API_LEVEL := 37
PRODUCT_USE_DYNAMIC_PARTITIONS := false
PRODUCT_BUILD_SUPER_PARTITION := false
PRODUCT_BUILD_BOOT_IMAGE := true
PRODUCT_BUILD_RAMDISK_IMAGE := true
PRODUCT_BUILD_VENDOR_BOOT_IMAGE := false
PRODUCT_BUILD_INIT_BOOT_IMAGE := false
PRODUCT_BUILD_RECOVERY_IMAGE := false
PRODUCT_BUILD_USERDATA_IMAGE := true
PRODUCT_OTA_ENFORCE_VINTF_KERNEL_REQUIREMENTS := false

# First-stage init with a board fstab in its ordinary gzip ramdisk.
# Do not inherit generic_ramdisk.mk: it forbids board files in the ramdisk.
PRODUCT_PACKAGES += \
    init_first_stage \
    ramdisk-build.prop \
    toolbox_ramdisk \
    init.zygote32.rc

PRODUCT_COPY_FILES += \
    $(FIREFLY_DEVICE_PATH)/prebuilts/zImage:kernel \
    $(FIREFLY_DEVICE_PATH)/init/fstab.fireflyrk3288:$(TARGET_COPY_OUT_RAMDISK)/fstab.fireflyrk3288 \
    $(FIREFLY_DEVICE_PATH)/init/fstab.fireflyrk3288:$(TARGET_COPY_OUT_VENDOR)/etc/fstab.fireflyrk3288 \
    $(FIREFLY_DEVICE_PATH)/init/init.fireflyrk3288.rc:$(TARGET_COPY_OUT_VENDOR)/etc/init/hw/init.fireflyrk3288.rc \
    $(FIREFLY_DEVICE_PATH)/init/ueventd.fireflyrk3288.rc:$(TARGET_COPY_OUT_VENDOR)/etc/ueventd.rc \
    $(FIREFLY_DEVICE_PATH)/permissions/firefly-hardware.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/firefly-hardware.xml

PRODUCT_VENDOR_PROPERTIES += \
    ro.zygote=zygote32 \
    ro.sf.lcd_density=160 \
    ro.config.low_ram=true \
    persist.sys.usb.config=adb \
    ro.com.android.dataroaming=false

# The board uses USB keyboard/mouse and Ethernet during first bring-up.
# No Wi-Fi/Bluetooth/camera feature is advertised before its HAL is adapted.
PRODUCT_PACKAGES += \
    android.hardware.health-service.example \
    android.hardware.power-service.example \
    android.hardware.memtrack-service.example \
    android.hardware.lights-service.example \
    android.hardware.security.keymint-service.nonsecure \
    com.android.hardware.gatekeeper.nonsecure \
    android.hardware.audio.service-aidl.firefly \
    android.hardware.audio.effect.service-aidl.firefly \
    firefly-remote \
    firefly-cec-input \
    FireflyTV \
    TvProvision \
    LeanbackIME \
    tinyplay \
    tinymix \
    tinypcminfo

PRODUCT_PACKAGES += \
    android.hardware.media.c2-service-firefly \
    firefly-vpu-probe \
    firefly-hwdecode

PRODUCT_COPY_FILES += \
    $(FIREFLY_DEVICE_PATH)/media/media_codecs.xml:$(TARGET_COPY_OUT_VENDOR)/etc/media_codecs.xml \
    $(FIREFLY_DEVICE_PATH)/media/media_codecs_firefly.xml:$(TARGET_COPY_OUT_VENDOR)/etc/media_codecs_firefly.xml

# Reference software Gatekeeper/KeyMint have no TEE isolation.
# Firefly audio uses the real HDMI ALSA PCM rather than the reference stub.

$(call inherit-product, $(SRC_TARGET_DIR)/product/updatable_apex.mk)
$(call inherit-product, frameworks/native/build/tablet-7in-hdpi-1024-dalvik-heap.mk)
$(call inherit-product, $(FIREFLY_DEVICE_PATH)/graphics/graphics.mk)

# Keep the first UI usable with HDMI and a mouse; no phone/radio dependencies.
DEVICE_PACKAGE_OVERLAYS += $(FIREFLY_DEVICE_PATH)/overlay
PRODUCT_AAPT_CONFIG := normal large xlarge mdpi hdpi xhdpi
PRODUCT_AAPT_PREF_CONFIG := hdpi
PRODUCT_SYSTEM_PROPERTIES += ro.adb.secure=1 persist.sys.timezone=Asia/Shanghai
PRODUCT_PRODUCT_PROPERTIES += ro.setupwizard.mode=DISABLED

PRODUCT_COPY_FILES += \
    $(FIREFLY_DEVICE_PATH)/audio/audio_policy_configuration.xml:$(TARGET_COPY_OUT_VENDOR)/etc/audio_policy_configuration.xml \
    $(FIREFLY_DEVICE_PATH)/audio/audio_effects_config.xml:$(TARGET_COPY_OUT_VENDOR)/etc/audio_effects_config.xml \
    frameworks/av/services/audiopolicy/config/r_submix_audio_policy_configuration.xml:$(TARGET_COPY_OUT_VENDOR)/etc/r_submix_audio_policy_configuration.xml \
    frameworks/av/services/audiopolicy/config/audio_policy_volumes.xml:$(TARGET_COPY_OUT_VENDOR)/etc/audio_policy_volumes.xml \
    frameworks/av/services/audiopolicy/config/default_volume_tables.xml:$(TARGET_COPY_OUT_VENDOR)/etc/default_volume_tables.xml \
    $(FIREFLY_DEVICE_PATH)/remote/ir-defaults.json:$(TARGET_COPY_OUT_VENDOR)/etc/firefly/ir-defaults.json \
    $(FIREFLY_DEVICE_PATH)/remote/gpio_ir_recv.kl:$(TARGET_COPY_OUT_VENDOR)/usr/keylayout/gpio_ir_recv.kl \
    $(FIREFLY_DEVICE_PATH)/remote/dw_hdmi.kl:$(TARGET_COPY_OUT_VENDOR)/usr/keylayout/dw_hdmi.kl

PRODUCT_VENDOR_PROPERTIES += ro.config.batteryless=true
PRODUCT_SYSTEM_PROPERTIES += \
    persist.sys.rotation=landscape \
    ro.surface_flinger.primary_display_orientation=ORIENTATION_0 \
    persist.device_config.activity_manager.max_cached_processes=8 \
    persist.device_config.activity_manager.max_phantom_processes=16

$(call inherit-product, $(FIREFLY_DEVICE_PATH)/apps/preloads.mk)
$(call inherit-product, $(FIREFLY_DEVICE_PATH)/tv-data/preloads.mk)

PRODUCT_PACKAGES += FireflyAdblockCMFA FireflyAdblockNotice

# External HDMI route monitor; analog remains the attached fallback.
PRODUCT_PACKAGES += FireflyHdmiAudio
