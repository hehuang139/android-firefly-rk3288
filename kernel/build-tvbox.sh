#!/bin/sh
# SPDX-License-Identifier: MIT
# Public release entry: never fall back to a historical bring-up kernel.
set -eu
kernel_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec sh "$kernel_dir/final/build-kernel.sh" "$@"
