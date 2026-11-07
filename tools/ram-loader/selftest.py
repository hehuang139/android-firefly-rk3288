#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline regression checks; requires a user-supplied original BOOT package."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
import patch_ram_readlimit as tool


def refused(action):
    try:
        action()
    except (ValueError, OSError):
        return
    raise RuntimeError("An invalid input was accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    original = args.input.read_bytes()
    before = tool.sha256(original)
    result, report = tool.patch_package(original)
    if tool.sha256(result) != tool.OUTPUT_SHA256 or len(result) != tool.SOURCE_BYTES:
        raise RuntimeError("Known expected output not reproduced")
    if tool.sha256(original) != before or args.input.read_bytes() != original:
        raise RuntimeError("Original input modified")

    unknown = [original[:-1], original+b"\0", result]
    for position in (0, tool.USBPLUG_OFFSET, len(original)-1):
        data = bytearray(original)
        data[position] ^= 1
        unknown.append(bytes(data))
    for data in unknown:
        refused(lambda: tool.patch_package(data))

    corrupted = bytearray(original)
    corrupted[tool.USBPLUG_OFFSET] ^= 1
    refused(lambda: tool.verify_structure(corrupted))
    malformed = bytearray(original)
    malformed[159] = 56
    struct.pack_into("<I", malformed, len(malformed)-4, tool.rockchip_crc32(malformed[:-4]))
    refused(lambda: tool.verify_structure(malformed))

    actual = 0x01D1F000  # Historical tested capacity, not a default for another board.
    tool.check_transfer_bounds(actual, 0xFF80, 128)
    tool.check_transfer_bounds(actual, 0x10000, 128)
    tool.check_transfer_bounds(actual, actual-1, 1)
    invalid_ranges = [(actual, actual-1, 2), (actual, actual, 1), (actual, -1, 1),
                      (actual, 0, 0), (actual, 0, 0x10000), (actual, 0xFFFFFFFF, 2),
                      (0, 0, 1), (tool.NEW_READ_LIMIT_SECTORS+1, 0, 1)]
    for values in invalid_ranges:
        refused(lambda: tool.check_transfer_bounds(*values))

    script = Path(tool.__file__).resolve()
    with tempfile.TemporaryDirectory(prefix="rk3288-offline-selftest-") as directory:
        output = Path(directory)/"test-RAM-ONLY.bin"
        command = [sys.executable, "-B", str(script), "--input", str(args.input),
                   "--output", str(output)]
        run = subprocess.run(command, capture_output=True, check=False)
        if run.returncode or output.read_bytes() != result:
            raise RuntimeError("CLI did not reproduce the expected output")
        run = subprocess.run(command, capture_output=True, check=False)
        if run.returncode == 0 or output.read_bytes() != result:
            raise RuntimeError("CLI overwrote an existing output")
        altered = Path(directory)/"unknown.bin"
        altered.write_bytes(unknown[3])
        destination = Path(directory)/"unknown-RAM-ONLY.bin"
        run = subprocess.run([sys.executable, "-B", "-O", str(script), "--input", str(altered),
                              "--output", str(destination)], capture_output=True, check=False)
        if run.returncode == 0 or destination.exists():
            raise RuntimeError("Unknown input accepted with Python optimizations enabled")
    print(json.dumps({
        "status": "passed", "hardware_access": False,
        "exact_input_sha256": before, "exact_output_sha256": tool.sha256(result),
        "unknown_inputs_rejected": len(unknown), "malformed_crc_or_structure_rejected": 2,
        "valid_transfer_ranges": 3, "invalid_transfer_ranges_rejected": len(invalid_ranges),
        "cli_exact_output": True, "cli_overwrite_refused": True,
        "python_optimized_validation_retained": True, "original_input_unchanged": True,
        "package_changed_offsets_hex": report["package_changed_offsets_hex"],
        "output_binaries_retained_by_selftest": False,
    }, indent=2))


if __name__ == "__main__":
    main()
