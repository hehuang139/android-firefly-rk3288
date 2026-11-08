# SPDX-License-Identifier: Apache-2.0
PRODUCT_COPY_FILES += \
    $(FIREFLY_DEVICE_PATH)/tv-data/channels.json:$(TARGET_COPY_OUT_PRODUCT)/etc/firefly-tv/channels.json \
    $(FIREFLY_DEVICE_PATH)/tv-data/epg.xml:$(TARGET_COPY_OUT_PRODUCT)/etc/firefly-tv/epg.xml \
    $(FIREFLY_DEVICE_PATH)/tv-data/epg-settings.json:$(TARGET_COPY_OUT_PRODUCT)/etc/firefly-tv/epg-settings.json
