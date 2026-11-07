#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail
work_root=$1
build_action=$2
jobs=${3:-12}
case "$jobs" in ''|*[!0-9]*) echo 'jobs must be an integer' >&2; exit 2;; esac
cd "$work_root/aosp"
export PATH="$work_root/tools/mesa-native/install/bin:$PATH"
export GOMAXPROCS="$jobs"
export GOMEMLIMIT=18GiB
export SOONG_GOMEMLIMIT=24GiB
export SOONG_GOGC=50
export SOONG_NINJA=ninja
export BUILD_USERNAME=builder
source build/envsetup.sh
case "$build_action" in
  lunch)
    lunch aosp_firefly_rk3288-aosp_current-userdebug
    get_build_var PRODUCT_OUT
    ;;
  graph|build|tools)
    # make-mode resolves the product configuration itself. Avoid a separate
    # lunch dumpvars/finder scan before that same work on every incremental run.
    export TARGET_PRODUCT=aosp_firefly_rk3288
    export TARGET_RELEASE=aosp_current
    export TARGET_BUILD_VARIANT=userdebug
    export TARGET_BUILD_TYPE=release
    export TARGET_BUILD_APPS=
    targets=(linkerconfig deapexer debugfs_static fsck.erofs host_init_verifier)
    case "$build_action" in
      graph) targets=(nothing);;
      build) targets=(droid "${targets[@]}");;
    esac
    build/soong/soong_ui.bash --make-mode -j"$jobs" -k10 "${targets[@]}"
    ;;
  *) echo 'action must be lunch, graph, build or tools' >&2; exit 2;;
esac
