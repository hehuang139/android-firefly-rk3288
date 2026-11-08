#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail
aosp_root=${FIREFLY_AOSP_ROOT:?Set FIREFLY_AOSP_ROOT to the isolated merged source}
export OUT_DIR=${FIREFLY_ANDROID_OUTPUT:?Set a new RK3399 output directory}
case "$OUT_DIR" in
  /*|../*|*/../*) echo 'Mount the independent output under the source tree and use a relative path (for example out)' >&2; exit 2;;
esac
action=${1:-graph}
jobs=${FIREFLY_ANDROID_JOBS:-6}
case "$jobs" in ''|*[!0-9]*) echo 'jobs must be a number' >&2; exit 2;; esac
((jobs >= 1 && jobs <= 16)) || { echo 'Use between one and sixteen build workers' >&2; exit 2; }
cd "$aosp_root"
test ! -e device/firefly/rk3288 || { echo 'RK3288 tree is still visible' >&2; exit 1; }
test -f device/firefly/rk3399/.firefly-port
export PATH="${FIREFLY_MESA_NATIVE_TOOLS:?Set matching Mesa native tool directory}:$PATH"
export GOMAXPROCS=${FIREFLY_SOONG_JOBS:-6}
export GOMEMLIMIT=12GiB
export SOONG_GOMEMLIMIT=${FIREFLY_SOONG_GOMEMLIMIT:-24GiB}
export SOONG_GOGC=50
export SOONG_NINJA=ninja
export FIREFLY_MESA_JOBS="$jobs"
export BUILD_USERNAME=builder
source build/envsetup.sh
export TARGET_PRODUCT=aosp_firefly_rk3399
export TARGET_RELEASE=aosp_current
export TARGET_BUILD_VARIANT=userdebug
export TARGET_BUILD_TYPE=release
export TARGET_BUILD_APPS=
case "$action" in
  lunch)
    lunch aosp_firefly_rk3399-aosp_current-userdebug
    build/soong/soong_ui.bash --dumpvars-mode --vars='TARGET_ARCH TARGET_2ND_ARCH TARGET_CPU_ABI TARGET_2ND_CPU_ABI PRODUCT_OUT OUT_DIR'
    ;;
  graph) build/soong/soong_ui.bash --make-mode -j"$jobs" nothing;;
  bootstrap) build/soong/soong_ui.bash --make-mode -j"$jobs" ndk_sysroot crtbegin_so crtbegin_dynamic crtend_so crtend_android;;
  components)
    build/soong/soong_ui.bash --make-mode -j"$jobs" FireflyTV TvSettings \
      android.hardware.audio.service-aidl.firefly android.hardware.audio.effect.service-aidl.firefly \
      android.hardware.media.c2-service-firefly firefly-vpu-probe firefly-hwdecode
    ;;
  build) build/soong/soong_ui.bash --make-mode -j"$jobs" droid;;
  *) echo 'action must be lunch, graph, bootstrap, components or build' >&2; exit 2;;
esac
