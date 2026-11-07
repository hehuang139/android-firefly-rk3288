#!/usr/bin/env python3
"""Check incremental-build input installation with old-timestamp overlays."""
# SPDX-License-Identifier: MIT
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "firefly_installer", Path(__file__).with_name("install-port.py"))
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class CopyBuildInputTest(unittest.TestCase):
    def test_old_timestamp_overlay_invalidates_existing_build(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "overlay.te"
            destination = Path(directory) / "installed.te"
            source.write_text("type new_property;\n")
            destination.write_text("type old_property;\n")
            # The cached output is newer than the overlay's recorded time.
            os.utime(source, ns=(1_000_000_000, 1_000_000_000))
            cached_output_time = 2_000_000_000
            os.utime(destination, ns=(cached_output_time, cached_output_time))
            INSTALLER.copy_build_input(source, destination)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertGreater(destination.stat().st_mtime_ns, cached_output_time)

    def test_reinstall_preserves_unchanged_input_time(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            destination = Path(directory) / "installed"
            source.write_text("unchanged build input\n")
            INSTALLER.copy_build_input(source, destination)
            original_time = destination.stat().st_mtime_ns
            INSTALLER.copy_build_input(source, destination)
            self.assertEqual(destination.stat().st_mtime_ns, original_time)

    def test_preserves_executable_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "tool"
            destination = Path(directory) / "installed-tool"
            source.write_text("#!/bin/sh\nexit 0\n")
            source.chmod(0o755)
            INSTALLER.copy_build_input(source, destination)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o755)


if __name__ == "__main__":
    unittest.main()
