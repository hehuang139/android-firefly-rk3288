#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check SD/eMMC contracts and source allowlists using private file fixtures."""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import tarfile
import tempfile


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    port = Path(__file__).resolve().parents[1]
    assemble = load("media_assemble", port / "scripts/assemble-sd.py")
    verify = load("media_verify", port / "scripts/verify-sd.py")
    package = load("media_package", port / "scripts/package-source.py")
    cases = []

    def passes(name, action):
        action()
        cases.append({"name": name, "passed": True})

    def rejects(name, action):
        try:
            action()
        except (ValueError, verify.VerificationError, package.PackagingError) as error:
            cases.append({"name": name, "passed": True, "rejection": str(error)})
        else:
            raise AssertionError("Expected rejection: " + name)

    with tempfile.TemporaryDirectory(prefix="firefly-media-test-") as temporary:
        scratch = Path(temporary)
        sd, emmc = scratch / "sd", scratch / "emmc"
        for directory in (sd, emmc):
            (directory / "boot").mkdir(parents=True)
            (directory / "extlinux").mkdir()
            shutil.copyfile(port / "device/firefly/rk3288/prebuilts/rk3288-firefly-android.dtb", directory / "boot/rk3288-firefly-android.dtb")
        shutil.copyfile(port / "boot/extlinux.conf", sd / "extlinux/extlinux.conf")
        emmc_config = (port / "boot/extlinux.conf").read_text().replace("ff0c0000.mmc", "ff0f0000.mmc")
        (emmc / "extlinux/extlinux.conf").write_text(emmc_config)
        emmc_dtb = emmc / "boot/rk3288-firefly-android.dtb"
        for node, prop, kind, value in (("/mmc@ff0f0000", "status", "s", "okay"),
                                        ("/mmc@ff0c0000", "status", "s", "disabled"),
                                        ("/mmc@ff0f0000", "max-frequency", "u", "50000000")):
            subprocess.run(["fdtput", "-t", kind, str(emmc_dtb), node, prop, value], check=True)

        def verify_files(directory, medium):
            audit = verify.Audit("media-file-fixture")
            verify.check_boot_medium_files(directory / "boot/rk3288-firefly-android.dtb", (directory / "extlinux/extlinux.conf").read_text(), medium, audit)

        passes("assembler default SD contract accepts current TF DTB/extlinux", lambda: assemble.check_boot_medium_files(sd))
        passes("verifier default SD contract accepts current TF DTB/extlinux", lambda: verify_files(sd, "sd"))
        passes("assembler eMMC DTB/extlinux contract", lambda: assemble.check_boot_medium_files(emmc, "emmc"))
        passes("verifier eMMC DTB/extlinux contract", lambda: verify_files(emmc, "emmc"))
        rejects("assembler rejects SD files for eMMC", lambda: assemble.check_boot_medium_files(sd, "emmc"))
        rejects("verifier rejects eMMC files for SD", lambda: verify_files(emmc, "sd"))
        (emmc / "extlinux/extlinux.conf").write_text(emmc_config.replace("androidboot.boot_devices=ff0f0000.mmc", "androidboot.boot_devices=ff0f0000.mmc androidboot.boot_devices=ff0c0000.mmc"))
        rejects("assembler rejects conflicting bootdevice arguments", lambda: assemble.check_boot_medium_files(emmc, "emmc"))
        rejects("verifier rejects conflicting bootdevice arguments", lambda: verify_files(emmc, "emmc"))
        (emmc / "extlinux/extlinux.conf").write_text(emmc_config)

        idb = port / "bootloader/idbloader.img"
        uboot = port / "bootloader/u-boot-dtb.img"
        passes("assembler default SD contract accepts current actual U-Boot", lambda: assemble.check_boot_medium_loaders(idb, uboot))
        passes("verifier SD contract accepts current actual U-Boot", lambda: verify.check_boot_medium_loaders(idb.read_bytes(), uboot.read_bytes(), "sd", verify.Audit("media-file-fixture"), scratch))
        rejects("assembler rejects SD U-Boot for eMMC", lambda: assemble.check_boot_medium_loaders(idb, uboot, "emmc"))
        rejects("verifier rejects SD U-Boot for eMMC", lambda: verify.check_boot_medium_loaders(idb.read_bytes(), uboot.read_bytes(), "emmc", verify.Audit("media-file-fixture"), scratch))
        # Only the media helper is under test here: these are partial payload
        # fixtures, not complete loaders or any assembled disk image.
        emmc_uboot = scratch / "emmc-bootcmd.fixture"
        emmc_uboot.write_bytes(b"\0bootcmd=" + assemble.BOOT_MEDIA["emmc"]["bootcmd"].encode() + b"\0")
        rejects("assembler rejects SD SPL even with eMMC bootcmd", lambda: assemble.check_boot_medium_loaders(idb, emmc_uboot, "emmc"))
        rejects("verifier rejects SD SPL even with eMMC bootcmd", lambda: verify.check_boot_medium_loaders(idb.read_bytes(), emmc_uboot.read_bytes(), "emmc", verify.Audit("media-file-fixture"), scratch))
        blob, offset = idb.read_bytes(), 0
        spl = scratch / "emmc-spl.fixture.dtb"
        while (offset := blob.find(b"\xd0\x0d\xfe\xed", offset)) >= 0:
            length = struct.unpack_from(">I", blob, offset + 4)[0]
            if 40 <= length <= len(blob) - offset:
                spl.write_bytes(blob[offset:offset + length])
                break
            offset += 4
        assert spl.exists()
        subprocess.run(["fdtput", "-t", "s", str(spl), "/chosen", "u-boot,spl-boot-order", "/mmc@ff0f0000"], check=True)
        emmc_idb = scratch / "emmc-spl.fixture"
        emmc_idb.write_bytes(b"isolated-spl-fixture\0" + spl.read_bytes())
        passes("assembler accepts eMMC-only embedded SPL FDT", lambda: assemble.check_boot_medium_loaders(emmc_idb, emmc_uboot, "emmc"))
        passes("verifier accepts eMMC-only embedded SPL FDT", lambda: verify.check_boot_medium_loaders(emmc_idb.read_bytes(), emmc_uboot.read_bytes(), "emmc", verify.Audit("media-file-fixture"), scratch))
        emmc_idb.write_bytes(emmc_idb.read_bytes() + spl.read_bytes())
        rejects("verifier rejects ambiguous multiple SPL policies", lambda: verify.check_boot_medium_loaders(emmc_idb.read_bytes(), emmc_uboot.read_bytes(), "emmc", verify.Audit("media-file-fixture"), scratch))

        source = scratch / "source"
        source.mkdir()
        for name in package.FILES:
            (source / name).write_text("source fixture\n")
        for name in package.DIRECTORIES:
            (source / name).mkdir(exist_ok=True)
        for relative in package.PREBUILTS:
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"binary fixture")
        for relative in ("variants/emmc/rebuild.sh", "variants/emmc/board.dts", "variants/emmc/out/source/linux-big.c", "variants/emmc/boot/zImage", "variants/emmc/records/uboot-spl.dtb"):
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")

        def packed(include):
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode="w") as archive:
                contents = package.Package(archive, include)
                descriptor = package.open_directory(source)
                try:
                    for name in package.FILES:
                        contents.add(descriptor, name, PurePosixPath(name), "file")
                    for name in package.DIRECTORIES:
                        contents.add(descriptor, name, PurePosixPath(name), "directory")
                    contents.finish()
                finally:
                    os.close(descriptor)
            data.seek(0)
            with tarfile.open(fileobj=data) as archive:
                return {name.removeprefix(package.ARCHIVE_ROOT + "/") for name in archive.getnames()}

        def check_source_only():
            names = packed(False)
            assert "variants/emmc/board.dts" in names and "variants/emmc/rebuild.sh" in names
            assert not names.intersection(package.PREBUILTS)
            assert "variants/emmc/records/uboot-spl.dtb" not in names
            assert not any(name.startswith("variants/emmc/out") for name in names)
            assert "variants/emmc/boot/zImage" not in names
        passes("source-only archive includes variant sources and excludes all built inputs/out tree", check_source_only)
        def check_prebuilts():
            names = packed(True)
            assert package.PREBUILTS <= names
            assert not any(name.startswith("variants/emmc/out") for name in names)
            assert "variants/emmc/boot/zImage" not in names
        passes("include-prebuilts contains both media without duplicate kernel/source build trees", check_prebuilts)
        (source / "variants/emmc/bootloader/idbloader.img").unlink()
        rejects("include-prebuilts requires actual eMMC loader", lambda: packed(True))

    report = {"result": "PASS", "scope": "actual current SD files plus private eMMC contract/SPL-FDT and source-tar fixtures",
              "image_generated": False, "image_verified": False, "actual_emmc_build_verification": "recorded separately after variant build",
              "cases_passed": len(cases), "cases": cases}
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
