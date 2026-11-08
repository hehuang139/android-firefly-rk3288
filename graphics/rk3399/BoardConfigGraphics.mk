# SPDX-License-Identifier: Apache-2.0
# Mali-T860 uses the Panfrost Gallium driver. PanVK is deliberately not selected.
BOARD_BUILD_AOSPEXT_MESA3D := true
BOARD_MESA3D_SRC_DIR := external/mesa3d
BOARD_MESA3D_GALLIUM_DRIVERS := panfrost
BOARD_MESA3D_VULKAN_DRIVERS :=
BOARD_MESA3D_BUILD_LIBGBM := false
# The CLC tools must come from exactly the same Mesa source checkout. Build
# graphics/host-tools first, then put its install/bin directory in PATH.
BOARD_MESA3D_EXTRA_MESON_ARGS := \
    -Dmesa-clc=system \
    -Dprecomp-compiler=system \
    -Dgbm=disabled \
    -Dglx=disabled \
    -Dgallium-va=disabled \
    -Dgallium-rusticl=false \
    -Dvideo-codecs= \
    -Dzstd=disabled \
    -Dbuild-tests=false

# minigbm's generic configuration includes rockchip.c automatically.
$(call soong_config_set,minigbm,platform,generic)
BOARD_VENDOR_SEPOLICY_DIRS += external/minigbm/cros_gralloc/sepolicy
