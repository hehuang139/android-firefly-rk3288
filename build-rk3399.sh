#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
port_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
action=${1:-help}
case "$action" in
  install)
    python3 "$port_root/scripts/install-rk3399-port.py" "${FIREFLY_AOSP_ROOT:?Set the isolated AOSP source path}"
    ;;
  lunch|graph|bootstrap|components|build)
    bash "$port_root/scripts/build-rk3399-inside.sh" "$action"
    ;;
  help|-h|--help)
    echo 'RK3399 source build: install, lunch, graph, bootstrap, components, build'
    echo 'Run inside the isolated unprivileged builder with FIREFLY_AOSP_ROOT,'
    echo 'FIREFLY_ANDROID_OUTPUT and FIREFLY_MESA_NATIVE_TOOLS set explicitly.'
    echo 'Use a different output tree from RK3288. This entry never flashes.'
    ;;
  *) echo "Unknown action: $action" >&2; exit 2;;
esac
