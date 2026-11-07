#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run inside the builder image, after inside.sh. Exercise the same shader
# generators that the Panfrost Gallium target build will invoke.
set -euo pipefail
mesa_source=$(realpath "$1")
native_output=$(realpath "$2")
verify_output="$native_output/shader-verification"
mkdir -p "$verify_output"
for pan_arch in 4 5 6 7 9 10 12 13; do
    "$native_output/install/bin/mesa_clc" \
        -o "$verify_output/libpan_v$pan_arch.spv" \
        "$mesa_source/src/panfrost/libpan/query_pool.cl" \
        "$mesa_source/src/panfrost/libpan/draw_helper.cl" \
        "$mesa_source/src/panfrost/libpan/indirect_dispatch.cl" -- \
        "-DPAN_ARCH=$pan_arch" \
        "-I$mesa_source/include" \
        "-I$mesa_source/src/compiler/libcl" \
        "-I$mesa_source/src/panfrost/libpan" \
        "-I$mesa_source/src" \
        "-I$mesa_source/src/panfrost" \
        "-I$native_output/build/src/panfrost" \
        -cl-std=cl2.0 -D__OPENCL_VERSION__=200 \
        -DHAVE___BUILTIN_FFS -DHAVE___BUILTIN_CLZ
    "$native_output/install/bin/vtn_bindgen2" \
        "$verify_output/libpan_v$pan_arch.spv" \
        "$verify_output/libpan_v$pan_arch.cpp" \
        "$verify_output/libpan_v$pan_arch.h"
    "$native_output/install/bin/panfrost_compile" libpan_shaders "$pan_arch" \
        "$verify_output/libpan_v$pan_arch.spv" \
        "$verify_output/libpan_shaders_v$pan_arch.h" \
        "$verify_output/libpan_shaders_v$pan_arch.c"
    echo "Panfrost libpan shader generators: architecture $pan_arch passed"
done
