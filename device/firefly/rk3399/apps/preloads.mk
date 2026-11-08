# SPDX-License-Identifier: Apache-2.0
# Empty by default. Add your independently obtained, licensed APK modules here.
# Keep APKs, signing keys and account data out of this repository.

# Generated only after explicit local validation of an independently obtained APK.
-include device/firefly/rk3399/apps/youtube-official/preload.mk
-include device/firefly/rk3399/apps/legacy-private/preloads.mk
ifneq ($(wildcard device/firefly/rk3399/apps/legacy-private/Android.mk),)
PRODUCT_ALLOWED_ANDROIDMK_FILES += device/firefly/rk3399/apps/legacy-private/Android.mk
endif
