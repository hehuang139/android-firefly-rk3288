# Review candidate. Stage verified files under $(FIREFLY_DEVICE_PATH)/wifi.
FIREFLY_WIFI_PATH := $(FIREFLY_DEVICE_PATH)/wifi
PRODUCT_PACKAGES += wpa_supplicant wificond FireflyWifiOverlay
PRODUCT_VENDOR_PROPERTIES += wifi.interface=wlan0
PRODUCT_COPY_FILES += \
    $(FIREFLY_WIFI_PATH)/wpa_supplicant.conf:$(TARGET_COPY_OUT_VENDOR)/etc/wifi/wpa_supplicant.conf \
    $(FIREFLY_WIFI_PATH)/android.hardware.wifi.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.wifi.xml \
    $(FIREFLY_WIFI_PATH)/init.firefly-wifi.rc:$(TARGET_COPY_OUT_VENDOR)/etc/init/init.firefly-wifi.rc \
    $(FIREFLY_WIFI_PATH)/firefly-wifi-prepare.sh:$(TARGET_COPY_OUT_VENDOR)/bin/firefly-wifi-prepare.sh \
    $(FIREFLY_WIFI_PATH)/prebuilts/modules/cfg80211.ko:$(TARGET_COPY_OUT_VENDOR)/lib/modules/cfg80211.ko \
    $(FIREFLY_WIFI_PATH)/prebuilts/modules/brcmutil.ko:$(TARGET_COPY_OUT_VENDOR)/lib/modules/brcmutil.ko \
    $(FIREFLY_WIFI_PATH)/prebuilts/modules/brcmfmac.ko:$(TARGET_COPY_OUT_VENDOR)/lib/modules/brcmfmac.ko \
    $(FIREFLY_WIFI_PATH)/prebuilts/modules/brcmfmac-wcc.ko:$(TARGET_COPY_OUT_VENDOR)/lib/modules/brcmfmac-wcc.ko \
    $(FIREFLY_WIFI_PATH)/prebuilts/modules/brcmfmac-cyw.ko:$(TARGET_COPY_OUT_VENDOR)/lib/modules/brcmfmac-cyw.ko \
    $(FIREFLY_WIFI_PATH)/prebuilts/modules/brcmfmac-bca.ko:$(TARGET_COPY_OUT_VENDOR)/lib/modules/brcmfmac-bca.ko \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/brcm/brcmfmac4335-sdio.bin:$(TARGET_COPY_OUT_VENDOR)/firmware/brcm/brcmfmac4335-sdio.bin \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/brcm/brcmfmac4339-sdio.bin:$(TARGET_COPY_OUT_VENDOR)/firmware/brcm/brcmfmac4339-sdio.bin \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/brcm/brcmfmac4335-sdio.firefly,firefly-rk3288.txt:$(TARGET_COPY_OUT_VENDOR)/firmware/brcm/brcmfmac4335-sdio.firefly,firefly-rk3288.txt \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/brcm/brcmfmac4339-sdio.firefly,firefly-rk3288.txt:$(TARGET_COPY_OUT_VENDOR)/firmware/brcm/brcmfmac4339-sdio.firefly,firefly-rk3288.txt \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/regulatory.db:$(TARGET_COPY_OUT_VENDOR)/firmware/regulatory.db \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/regulatory.db.p7s:$(TARGET_COPY_OUT_VENDOR)/firmware/regulatory.db.p7s \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/licenses/LICENCE.broadcom_bcm43xx:$(TARGET_COPY_OUT_VENDOR)/etc/wifi/licenses/LICENCE.broadcom_bcm43xx \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/licenses/LICENCE.cypress:$(TARGET_COPY_OUT_VENDOR)/etc/wifi/licenses/LICENCE.cypress \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/licenses/linux-firmware-copyright:$(TARGET_COPY_OUT_VENDOR)/etc/wifi/licenses/linux-firmware-copyright \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/licenses/wireless-regdb-copyright:$(TARGET_COPY_OUT_VENDOR)/etc/wifi/licenses/wireless-regdb-copyright
# The supplicant module supplies its AIDL V5 VINTF fragment and RC itself.
# No android.hardware.wifi IWifi HAL is declared; no P2P/AP/Passpoint/Bluetooth
# feature is advertised by this minimum station candidate.
