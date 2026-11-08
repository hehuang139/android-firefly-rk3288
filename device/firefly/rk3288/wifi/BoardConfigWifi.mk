# Review candidate for the original Firefly RK3288 (station mode only).
# Include from BoardConfig.mk after copying this folder under device/.../wifi.
BOARD_WPA_SUPPLICANT_DRIVER := NL80211
WPA_SUPPLICANT_VERSION := VER_0_8_X
WPA_SUPPLICANT_USE_STUB_LIB := true
WIFI_HIDL_UNIFIED_SUPPLICANT_SERVICE_RC_ENTRY := true
# Do not select bcmdhd vendor HAL: this candidate uses mainline brcmfmac.
# WifiNative in this checkout supports a no-vendor-HAL station fallback.
