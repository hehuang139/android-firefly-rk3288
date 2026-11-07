#!/usr/bin/env python3
"""Install this board port into a separately synced AOSP tree."""
# SPDX-License-Identifier: MIT
import argparse
import filecmp
import hashlib
import pathlib
import shutil
import subprocess
import sys


ADB_BASE_COMMIT = "9084198a2d4b0f6a0f174260fb42da33485b684d"
ADB_PATCH = "0001-adbd-disable-implicit-network-fallback.patch"
SOONG_BASE_COMMIT = "6722dd8833db7482df1a2543ca3fcf67ddf0f7b1"
SOONG_PATCH = "0002-soong-configurable-go-memory.patch"
CORE_BASE_COMMIT = "545d2487e38192a2ce25040897ced877cf6b4f53"
HOSTS_PATCH = "0003-rootdir-adblock-hosts.patch"


def apply_release_patch(aosp, source, project, relative_file, patch_name,
                        base_commit, original_sha256, final_sha256):
    """Apply an exact release patch, accepting only verified base/final input."""
    module = aosp / project
    target = module / relative_file
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=module,
                          text=True, capture_output=True, check=True).stdout.strip()
    if head != base_commit:
        raise RuntimeError(f"{project} requires {base_commit}; found {head}")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest == final_sha256:
        print(f"Release patch already applied: {patch_name}")
        return
    if digest != original_sha256:
        raise RuntimeError(f"{project}/{relative_file} has unrelated local changes")
    patch = source / "patches" / patch_name
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=module, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=module, check=True)
    if hashlib.sha256(target.read_bytes()).hexdigest() != final_sha256:
        raise RuntimeError(f"Unexpected patched content: {target}")


def apply_release_patches(aosp, source):
    apply_release_patch(aosp, source, "external/minigbm",
        "cros_gralloc/cros_gralloc_driver.cc",
        "minigbm/0001-release-drm-master-and-allow-nv12-textures.patch",
        "ce79bbee67b3e2ea7abb110e1415e9ceceaa6471",
        "98e9054d5f98c3d107c25be6ac240c0b4bb858717860657641479595d3ec3103",
        "5ae73cb63c984d75f96582c71065c6e90eafd0c67a774462bfbe1d0451734a71")
    apply_release_patch(aosp, source, "packages/modules/Connectivity",
        "bpf/loader/NetBpfLoad.cpp",
        "connectivity/0001-firefly-arm32-bpf-compat.patch",
        "347fbd34b368d19f0d87e908ea101eed3601a731",
        "3438d20ed7c0510e3ee1f11777c7d134e6571129269556964a5fe6dfeb107055",
        "b5d279f14235e9c04cd622fa0430fb19eeed8f098ee494d2d3a075810b7ace63")


def copy_build_input(source, destination):
    """Refresh changed inputs even when an overlay preserves an older mtime."""
    if (pathlib.Path(destination).is_file()
            and filecmp.cmp(source, destination, shallow=False)):
        shutil.copymode(source, destination)
        return destination
    # copy2 can give new contents a timestamp older than a previous build's
    # output. Ninja then considers that output current and reuses stale policy.
    shutil.copyfile(source, destination)
    shutil.copymode(source, destination)
    return destination


def apply_hosts_patch(aosp, source):
    """Keep the single upstream etc_hosts producer, replacing its pinned input."""
    module = aosp / "system/core"
    patch = source / "patches" / HOSTS_PATCH
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=module,
                          text=True, capture_output=True, check=True).stdout.strip()
    if head != CORE_BASE_COMMIT:
        raise RuntimeError(f"TV hosts patch requires {CORE_BASE_COMMIT}; found {head}")
    forward = subprocess.run(["git", "apply", "--check", str(patch)], cwd=module,
                             text=True, capture_output=True)
    if forward.returncode == 0:
        subprocess.run(["git", "apply", str(patch)], cwd=module, check=True)
        print(f"Applied TV hosts patch: {patch.name}")
    else:
        reverse = subprocess.run(["git", "apply", "--reverse", "--check", str(patch)],
                                 cwd=module, text=True, capture_output=True)
        if reverse.returncode:
            raise RuntimeError("TV hosts patch conflicts with local edits.\n" + forward.stderr)
        print(f"TV hosts patch already applied: {patch.name}")
    expected = (source / "device/firefly/rk3288/adblock/hosts").read_bytes()
    if (module / "rootdir/etc/hosts").read_bytes() != expected:
        raise RuntimeError("Installed upstream hosts input differs from the TV filter list")


def apply_soong_patch(aosp, source):
    module = aosp / "build/soong"
    patch = source / "patches" / SOONG_PATCH
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=module,
                          text=True, capture_output=True, check=True).stdout.strip()
    if head != SOONG_BASE_COMMIT:
        raise RuntimeError(f"Soong host-memory patch requires {SOONG_BASE_COMMIT}; found {head}")
    forward = subprocess.run(["git", "apply", "--check", str(patch)], cwd=module,
                             text=True, capture_output=True)
    if forward.returncode == 0:
        subprocess.run(["git", "apply", str(patch)], cwd=module, check=True)
        print(f"Applied Soong host-memory patch: {patch.name}")
        return
    reverse = subprocess.run(["git", "apply", "--reverse", "--check", str(patch)],
                             cwd=module, text=True, capture_output=True)
    if reverse.returncode == 0:
        print(f"Soong host-memory patch already applied: {patch.name}")
        return
    raise RuntimeError("Soong patch matches neither its clean base nor applied state.\n"
                       + forward.stderr.strip() + "\n" + reverse.stderr.strip())


def apply_adbd_patch(aosp, source):
    """Apply the fixed-tag patch, accepting an exact prior application."""
    module = aosp / "packages/modules/adb"
    patch = source / "patches" / ADB_PATCH
    if not patch.is_file():
        raise RuntimeError(f"Missing required source patch: {patch}")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=module,
                          text=True, capture_output=True, check=True).stdout.strip()
    if head != ADB_BASE_COMMIT:
        raise RuntimeError("adbd patch requires android-17.0.0_r1 commit "
                           f"{ADB_BASE_COMMIT}; found {head}")
    command = ["git", "apply", "--check", str(patch)]
    forward = subprocess.run(command, cwd=module, text=True, capture_output=True)
    if forward.returncode == 0:
        subprocess.run(["git", "apply", str(patch)], cwd=module, check=True)
        print(f"Applied adbd USB-only default patch: {patch.name}")
        return
    reverse = subprocess.run(["git", "apply", "--reverse", "--check", str(patch)],
                             cwd=module, text=True, capture_output=True)
    if reverse.returncode == 0:
        print(f"adbd USB-only default patch already applied: {patch.name}")
        return
    raise RuntimeError("adbd patch matches neither the clean base nor its applied state; "
                       "preserve local edits and resolve this conflict before installing.\n"
                       + forward.stderr.strip() + "\n" + reverse.stderr.strip())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("aosp", type=pathlib.Path)
    args = p.parse_args()
    source = pathlib.Path(__file__).resolve().parents[1]
    aosp = args.aosp.resolve()
    if not (aosp / ".repo/manifest.xml").is_file():
        p.error("AOSP tree has not been initialized with repo")
    dest = aosp / "device/firefly/rk3288"
    marker = dest / ".firefly-port"
    if dest.exists() and not marker.is_file():
        p.error(f"Refusing to overwrite an unrelated device tree: {dest}")
    for name in ("device/firefly/rk3288", "graphics"):
        if not (source / name).is_dir():
            p.error(f"Missing port input: {name}")
    try:
        apply_adbd_patch(aosp, source)
        apply_soong_patch(aosp, source)
        apply_hosts_patch(aosp, source)
        apply_release_patches(aosp, source)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        p.error(str(error))
    dest.mkdir(parents=True, exist_ok=True)
    marker.write_text("Managed by firefly-rk3288 Android port/scripts/install-port.py\n")
    shutil.copytree(source / "device/firefly/rk3288", dest, dirs_exist_ok=True,
                    copy_function=copy_build_input)
    shutil.copytree(source / "graphics", dest / "graphics", dirs_exist_ok=True,
                    copy_function=copy_build_input)
    print(f"Installed board and graphics integration: {dest}")


if __name__ == "__main__":
    sys.exit(main())
