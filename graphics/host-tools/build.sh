#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
if (( $# != 2 )); then
    echo "Usage: $0 AOSP_ROOT OUTPUT_DIR" >&2
    exit 2
fi
aosp_root=$(realpath "$1")
output_dir=$(realpath -m "$2")
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mesa_source="$aosp_root/external/mesa3d"
if [[ ! -f "$mesa_source/meson.build" || ! -f "$mesa_source/VERSION" ]]; then
    echo "Mesa checkout is missing: $mesa_source" >&2
    exit 1
fi
mesa_commit=$(git -C "$mesa_source" rev-parse HEAD)
expected_commit=875160ed32cc5bc32777fa04870a0a57ed38c987
if [[ "$mesa_commit" != "$expected_commit" ]]; then
    echo "Mesa must match android-17.0.0_r1: $mesa_commit != $expected_commit" >&2
    exit 1
fi
builder_image=${FIREFLY_ANDROID_BUILDER_IMAGE:-firefly-android17-builder:20261104}
docker build --tag "$builder_image" "$script_dir"
mkdir -p "$output_dir"
builder_image_id=$(docker image inspect --format '{{.Id}}' "$builder_image")
docker run --rm --user "$(id -u):$(id -g)" \
    --volume "$aosp_root:$aosp_root:ro" \
    --volume "$output_dir:$output_dir" \
    --volume "$script_dir:$script_dir:ro" \
    --env "MESA_NATIVE_JOBS=${MESA_NATIVE_JOBS:-8}" \
    --workdir "$output_dir" \
    "$builder_image_id" bash "$script_dir/inside.sh" "$mesa_source" "$output_dir"
printf '%s\n' "$builder_image" > "$output_dir/builder-image.txt"
printf '%s\n' "$mesa_commit" > "$output_dir/mesa-commit.txt"
printf '%s\n' "$builder_image_id" > "$output_dir/builder-image-id.txt"
echo "Native Mesa tools: $output_dir/install/bin"
echo "Run the Android build inside $builder_image with this directory in PATH."
