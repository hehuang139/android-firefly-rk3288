# Original Firefly-RK3399 AP6356S candidate. Real scan/association still untested.
FIREFLY_WIFI_PATH := $(FIREFLY_DEVICE_PATH)/wifi
PRODUCT_PACKAGES += wpa_supplicant wificond FireflyWifiOverlay
PRODUCT_VENDOR_PROPERTIES += wifi.interface=wlan0
PRODUCT_COPY_FILES += \
    $(FIREFLY_WIFI_PATH)/wpa_supplicant.conf:$(TARGET_COPY_OUT_VENDOR)/etc/wifi/wpa_supplicant.conf \
    $(FIREFLY_WIFI_PATH)/android.hardware.wifi.xml:$(TARGET_COPY_OUT_VENDOR)/etc/permissions/android.hardware.wifi.xml \
    $(FIREFLY_WIFI_PATH)/init.firefly-wifi.rc:$(TARGET_COPY_OUT_VENDOR)/etc/init/init.firefly-wifi.rc \
    $(FIREFLY_WIFI_PATH)/firefly-wifi-prepare.sh:$(TARGET_COPY_OUT_VENDOR)/bin/firefly-wifi-prepare.sh
$(foreach module,cfg80211 brcmutil brcmfmac brcmfmac-wcc brcmfmac-cyw brcmfmac-bca,\
    $(eval PRODUCT_COPY_FILES += $(FIREFLY_WIFI_PATH)/prebuilts/modules/$(module).ko:$(TARGET_COPY_OUT_VENDOR)/lib/modules/$(module).ko))
PRODUCT_COPY_FILES += \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/brcm/brcmfmac4356-sdio.bin:$(TARGET_COPY_OUT_VENDOR)/firmware/brcm/brcmfmac4356-sdio.bin \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/brcm/brcmfmac4356-sdio.clm_blob:$(TARGET_COPY_OUT_VENDOR)/firmware/brcm/brcmfmac4356-sdio.clm_blob \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/brcm/brcmfmac4356-sdio.firefly,firefly-rk3399.txt:$(TARGET_COPY_OUT_VENDOR)/firmware/brcm/brcmfmac4356-sdio.firefly,firefly-rk3399.txt \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/regulatory.db:$(TARGET_COPY_OUT_VENDOR)/firmware/regulatory.db \
    $(FIREFLY_WIFI_PATH)/prebuilts/firmware/regulatory.db.p7s:$(TARGET_COPY_OUT_VENDOR)/firmware/regulatory.db.p7s
$(foreach license,LICENCE.broadcom_bcm43xx LICENCE.cypress linux-firmware-copyright wireless-regdb-copyright,\
    $(eval PRODUCT_COPY_FILES += $(FIREFLY_WIFI_PATH)/prebuilts/firmware/licenses/$(license):$(TARGET_COPY_OUT_VENDOR)/etc/wifi/licenses/$(license)))
