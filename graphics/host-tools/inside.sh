#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
mesa_source=$1
output_dir=$2
export CC=clang-19 CXX=clang++-19 LLVM_CONFIG=/usr/bin/llvm-config-19
export PKG_CONFIG_PATH="/usr/lib/llvm-19/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
setup_flags=()
if [[ -f "$output_dir/build/meson-private/coredata.dat" ]]; then
    setup_flags+=(--reconfigure)
fi
meson setup "${setup_flags[@]}" "$output_dir/build" "$mesa_source" \
    --prefix="$output_dir/install" --buildtype=release \
    -Dplatforms= -Dgallium-drivers= -Dvulkan-drivers= \
    -Dglx=disabled -Degl=disabled -Dgbm=disabled \
    -Dopengl=false -Dgles1=disabled -Dgles2=disabled \
    -Dmesa-clc=enabled -Dinstall-mesa-clc=true \
    -Dtools=panfrost -Dinstall-precomp-compiler=true \
    -Dgallium-rusticl=false -Dbuild-tests=false
meson compile -C "$output_dir/build" -j "${MESA_NATIVE_JOBS:-8}"
meson install -C "$output_dir/build"
for tool_name in mesa_clc vtn_bindgen2 panfrost_compile; do
    test -x "$output_dir/install/bin/$tool_name"
done
bash "$(dirname -- "${BASH_SOURCE[0]}")/verify.sh" "$mesa_source" "$output_dir"
dpkg-query -W -f='${Package}\t${Version}\n' > "$output_dir/host-packages.tsv"
meson introspect "$output_dir/build" --buildoptions > "$output_dir/meson-buildoptions.json"
