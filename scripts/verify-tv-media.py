#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Audit installed TV media ELF dependencies in their vendor linker namespace.

Reuses the existing ARM32 namespace/symbol checker without changing its core.
Fresh installed APEX payloads provide runtime libraries; Soong intermediates and
link-time stubs are excluded. This audit does not decode video or test audio.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile


MEDIA_ROOTS = (
    ("codec2-service", "/vendor/bin/hw/android.hardware.media.c2-service-firefly"),
    ("avcodec", "/vendor/lib/libavcodec.so"),
    ("avutil", "/vendor/lib/libavutil.so"),
    ("swscale", "/vendor/lib/libswscale.so"),
    ("vpu-probe", "/vendor/bin/firefly-vpu-probe"),
    ("hwdecode", "/vendor/bin/firefly-hwdecode"),
)
AUDIO_ROOTS = (
    ("audio-service", "/vendor/bin/hw/android.hardware.audio.service-aidl.firefly"),
    ("audio-effect-service", "/vendor/bin/hw/android.hardware.audio.effect.service-aidl.firefly"),
)
REMOTE_ROOTS = (
    ("remote", "/vendor/bin/firefly-remote"),
    ("cec-input", "/vendor/bin/firefly-cec-input"),
)


def load_core():
    path = Path(__file__).resolve().with_name("verify-graphics-elf.py")
    spec = importlib.util.spec_from_file_location("firefly_tv_elf_core", path)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    return core, path


def roots_for(args, parser):
    roots = list(MEDIA_ROOTS)
    if args.include_audio:
        roots.extend(AUDIO_ROOTS)
    if args.include_remote:
        roots.extend(REMOTE_ROOTS)
    paths = {item[1] for item in roots}
    for index, path in enumerate(args.extra_vendor_root):
        parts = PurePosixPath(path).parts
        if (len(parts) < 4 or parts[:2] != ("/", "vendor")
                or parts[2] not in ("bin", "lib") or ".." in parts):
            parser.error("Extra roots must be absolute /vendor/bin or /vendor/lib paths")
        if path in paths:
            parser.error("Duplicate extra root: " + path)
        paths.add(path)
        roots.append(("extra-" + str(index + 1), path))
    return tuple((name, "vendor", "default", path, ()) for name, path in roots)


def describe(report, core_path, roots):
    report.pop("graphics_verified", None)
    report["scope"] = "final installed ARM32 TV vendor ELF namespace and symbol dependency audit"
    report["tv_vendor_elf_verified"] = report.get("passed", False)
    report["hardware_decode_verified"] = False
    report["audio_playback_verified"] = False
    report["verification_core_sha256"] = hashlib.sha256(core_path.read_bytes()).hexdigest()
    report["selected_elf_roots"] = [item[3] for item in roots]
    requirements = report.get("requirements")
    if requirements:
        requirements["elf_roots"] = requirements.pop("graphics_roots")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aosp", type=Path, required=True)
    parser.add_argument("--product-out", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--work-dir", type=Path,
                        help="Existing empty directory for extracted APEX and linker configuration")
    parser.add_argument("--include-audio", action="store_true")
    parser.add_argument("--include-remote", action="store_true")
    parser.add_argument("--extra-vendor-root", action="append", default=[])
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--requirements", action="store_true")
    modes.add_argument("--check-tools", action="store_true")
    args = parser.parse_args()
    roots = roots_for(args, parser)
    core, core_path = load_core()
    core.ROOTS = roots
    aosp = args.aosp.resolve()
    product = (args.product_out or aosp / "out/target/product/rk3288").resolve()
    code = 0
    try:
        if args.requirements:
            report = {"result": "REQUIREMENTS", "requirements": core.requirements(aosp, product)}
        elif args.check_tools:
            tools = core.check_tools(aosp, product)
            report = {"result": "TOOLS_READY", "tools": {key: str(value) for key, value in tools.items()}}
        elif args.work_dir:
            report = core.verify_graphics_elf(product, aosp, args.work_dir)
        else:
            with tempfile.TemporaryDirectory(prefix="firefly-tv-elf-") as temporary:
                report = core.verify_graphics_elf(product, aosp, Path(temporary))
    except core.VerificationError as error:
        report = error.report or {"result": "FAIL", "error": str(error)}
        code = 1
    report = describe(report, core_path, roots)
    text = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(text)
    print(text, end="")
    return code


if __name__ == "__main__":
    sys.exit(main())
