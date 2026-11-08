#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Negative firmware-input tests: wrong ABI, truncated ELF and ARM64 relocation.

Synthetic data here only exercises rejection rules; it is never a boot image.
Run on Linux, where the read-only no-follow file reader is supported.
"""
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load("rk3399_verify", "verify-rk3399.py")
assemble = load("rk3399_assemble", "assemble-rk3399.py")


@unittest.skipUnless(os.name == "posix", "Requires POSIX read-only file primitives")
class FirmwareContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def elf(self, machine=183, interpreter=None, truncate=False):
        ident = b"\x7fELF\x02\x01\x01" + bytes(9)
        count = 2 if interpreter else 1
        data = struct.pack("<16sHHIQQQIHHHHHH", ident, 3, machine, 1, 0, 64, 0, 0, 64, 56, count, 0, 0, 0)
        data += struct.pack("<IIQQQQQQ", 1, 5, 0, 0, 0, 64, 64, 4096)
        if interpreter:
            text = interpreter.encode() + b"\0"
            data += struct.pack("<IIQQQQQQ", 3, 4, 176, 0, 0, len(text), len(text), 1) + text
        path = self.root / "test.elf"
        path.write_bytes(data[:-10] if truncate else data)
        return path

    def test_aarch64_header(self):
        self.assertEqual(check.elf64(self.elf())["machine"], "AArch64")

    def test_rejects_wrong_machine(self):
        for machine in (40, 62):
            with self.subTest(machine=machine), self.assertRaises(check.v.VerificationError):
                check.elf64(self.elf(machine=machine))

    def test_rejects_arm32_linker(self):
        with self.assertRaises(check.v.VerificationError):
            check.elf64(self.elf(interpreter="/system/bin/linker"))

    def test_rejects_truncated_program_headers(self):
        with self.assertRaises(check.v.VerificationError):
            check.elf64(self.elf(truncate=True))

    def test_bootstrap_linker_allowed_only_for_init(self):
        path = self.elf(interpreter="/system/bin/bootstrap/linker64")
        with self.assertRaises(check.v.VerificationError):
            check.elf64(path)
        self.assertEqual(check.elf64(path, "/system/bin/init")["interpreter"], "/system/bin/bootstrap/linker64")

    def boot_inputs(self):
        (self.root / "boot").mkdir()
        (self.root / "boot/ramdisk.img").write_bytes(b"test-only-not-bootable")
        (self.root / "boot/rk3399-firefly-android.dtb").write_bytes(b"test-only-not-bootable")
        kernel = bytearray(64)
        kernel[56:60] = b"ARM\x64"
        struct.pack_into("<QQQ", kernel, 8, 0, 32 * 1024 * 1024, 8)
        (self.root / "boot/Image").write_bytes(kernel)
        idb, fit = self.root / "idbloader.img", self.root / "u-boot.itb"
        idb.write_bytes(b"test-only-not-bootable")
        fit.write_bytes(bytes.fromhex("d00dfeed") + b"test-only-not-bootable")
        record = {"status": "OFFLINE_BUILD_VALIDATED_NOT_BOOTED", "board": "original Firefly-RK3399 DDR3",
                  "spl_boot_order": "/mmc@fe330000 only", "environment": "nowhere",
                  "default_environment": {"boot_targets": "mmc0", "bootcmd": "bootflow scan -lbG mmc0",
                    "kernel_addr_r": "0x02000000", "fdt_addr_r": "0x01f00000", "ramdisk_addr_r": "0x06000000"},
                  "assets": {p.name: {"bytes": p.stat().st_size, "sha256": assemble.digest(p)} for p in (idb, fit)}}
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps(record))
        return idb, fit, manifest, self.root

    def test_detects_image_memory_overlap_beyond_file_size(self):
        args = self.boot_inputs()
        assemble.check_boot_medium_loaders(*args)
        image = self.root / "boot/Image"
        data = bytearray(image.read_bytes())
        struct.pack_into("<Q", data, 16, 96 * 1024 * 1024)
        image.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "overlap"):
            assemble.check_boot_medium_loaders(*args)

    def test_rejects_relocating_legacy_load_address(self):
        args = self.boot_inputs()
        record = json.loads(args[2].read_text())
        record["default_environment"]["kernel_addr_r"] = "0x02080000"
        args[2].write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "aligned ARM64"):
            assemble.check_boot_medium_loaders(*args)

    def test_rejects_image_without_anywhere_placement_flag(self):
        args = self.boot_inputs()
        image = self.root / "boot/Image"
        data = bytearray(image.read_bytes())
        struct.pack_into("<Q", data, 24, 0)
        image.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "aligned ARM64"):
            assemble.check_boot_medium_loaders(*args)

    def test_rejects_unbound_loader_bytes(self):
        args = self.boot_inputs()
        args[0].write_bytes(b"different-loader")
        with self.assertRaisesRegex(ValueError, "differs"):
            assemble.check_boot_medium_loaders(*args)


if __name__ == "__main__":
    unittest.main()
