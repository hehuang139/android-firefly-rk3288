# SPDX-License-Identifier: Apache-2.0
FIREFLY_DEVICE_PATH := device/firefly/rk3399

include build/make/target/board/BoardConfigMainlineCommon.mk

# Cortex-A72/A53 share ARMv8-A. Keep both ABIs for existing Android TV apps.
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_VARIANT := cortex-a53
TARGET_CPU_ABI := arm64-v8a
TARGET_2ND_ARCH := arm
TARGET_2ND_ARCH_VARIANT := armv8-a
TARGET_2ND_CPU_VARIANT := generic
TARGET_2ND_CPU_ABI := armeabi-v7a
TARGET_2ND_CPU_ABI2 := armeabi
TARGET_SUPPORTS_32_BIT_APPS := true
TARGET_SUPPORTS_64_BIT_APPS := true
TARGET_ENABLE_MEDIADRM_64 := true
# Both userspaces use the 64-bit Binder UAPI of the ARM64 kernel.

TARGET_BOARD_PLATFORM := rk3399
TARGET_BOOTLOADER_BOARD_NAME := firefly-rk3399
TARGET_NO_BOOTLOADER := true
TARGET_NO_RECOVERY := true
TARGET_NO_KERNEL := false
TARGET_PREBUILT_KERNEL := $(FIREFLY_DEVICE_PATH)/prebuilts/Image
BOARD_PREBUILT_DTBIMAGE_DIR := $(FIREFLY_DEVICE_PATH)/prebuilts

# U-Boot boots ARM64 Image, ramdisk.img and the DTB directly from FAT/extlinux.
# boot.img is also built as a reproducible packaging/inspection artifact.
BOARD_BOOT_HEADER_VERSION := 2
BOARD_INCLUDE_DTB_IN_BOOTIMG := true
BOARD_KERNEL_BASE := 0x00000000
BOARD_KERNEL_PAGESIZE := 4096
BOARD_KERNEL_OFFSET := 0x02000000
BOARD_RAMDISK_OFFSET := 0x06000000
BOARD_DTB_OFFSET := 0x01f00000
BOARD_MKBOOTIMG_ARGS += --header_version $(BOARD_BOOT_HEADER_VERSION)
BOARD_MKBOOTIMG_ARGS += --kernel_offset $(BOARD_KERNEL_OFFSET)
BOARD_MKBOOTIMG_ARGS += --ramdisk_offset $(BOARD_RAMDISK_OFFSET)
BOARD_MKBOOTIMG_ARGS += --dtb_offset $(BOARD_DTB_OFFSET)
BOARD_KERNEL_CMDLINE := console=ttyS2,1500000n8 console=tty1
BOARD_KERNEL_CMDLINE += androidboot.hardware=fireflyrk3399 androidboot.selinux=permissive
BOARD_KERNEL_CMDLINE += androidboot.boot_devices=fe330000.mmc
BOARD_KERNEL_CMDLINE += androidboot.verifiedbootstate=orange androidboot.flash.locked=0
BOARD_KERNEL_CMDLINE += firmware_class.path=/vendor/firmware
BOARD_RAMDISK_USE_LZ4 := false
# This variable uses nonempty/empty conversion in Soong's filesystem config.
BOARD_USES_GENERIC_KERNEL_IMAGE :=
BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864

# Static GPT partition names must match init/fstab.fireflyrk3399 and image packer.
# AVB, A/B, dynamic partitions and encryption are deliberately absent in alpha.
BOARD_AVB_ENABLE := false
BOARD_USES_SYSTEM_OTHER_ODEX := false
BOARD_FLASH_BLOCK_SIZE := 4096
TARGET_USERIMAGES_USE_EXT4 := true
TARGET_USERIMAGES_SPARSE_EXT_DISABLED := true
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_SYSTEMIMAGE_PARTITION_SIZE := 4294967296
TARGET_COPY_OUT_SYSTEM_EXT := system_ext
BOARD_SYSTEM_EXTIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_SYSTEM_EXTIMAGE_PARTITION_SIZE := 1073741824
TARGET_COPY_OUT_PRODUCT := product
BOARD_PRODUCTIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_PRODUCTIMAGE_PARTITION_SIZE := 1073741824
TARGET_COPY_OUT_VENDOR := vendor
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE := ext4
BOARD_VENDORIMAGE_PARTITION_SIZE := 536870912
BOARD_USES_METADATA_PARTITION := true
BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE := ext4
# The image packer expands this filesystem to the actual userdata partition.
BOARD_USERDATAIMAGE_PARTITION_SIZE := 5368709120

DEVICE_MANIFEST_FILE := $(FIREFLY_DEVICE_PATH)/manifest.xml
DEVICE_MATRIX_FILE := $(FIREFLY_DEVICE_PATH)/compatibility_matrix.xml
DEVICE_FRAMEWORK_COMPATIBILITY_MATRIX_FILE += $(FIREFLY_DEVICE_PATH)/remote/framework-compatibility-matrix.xml
DEVICE_FRAMEWORK_COMPATIBILITY_MATRIX_FILE += $(FIREFLY_DEVICE_PATH)/media/framework-compatibility-matrix.xml
BOARD_VENDOR_SEPOLICY_DIRS += $(FIREFLY_DEVICE_PATH)/sepolicy/vendor

include $(FIREFLY_DEVICE_PATH)/graphics/BoardConfigGraphics.mk

# Enable only after matching RK3399 modules, firmware and calibration are staged.
FIREFLY_ENABLE_WIFI ?= false
ifeq ($(FIREFLY_ENABLE_WIFI),true)
include $(FIREFLY_DEVICE_PATH)/wifi/BoardConfigWifi.mk
endif
