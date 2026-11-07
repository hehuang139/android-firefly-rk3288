#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline exact-input RK3288 RAM usbplug read-limit correction. No device I/O."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

SOURCE_SHA256 = "b81f18bed5120111b01cafab7de45f27281f6ed3d9c3ea5c077c48debbd74218"
OUTPUT_SHA256 = "246f1e3adf3ebdae8e460a8c9570cd195f73fe93a2577524fe8fb8b5a118461f"
SOURCE_BYTES = 209230
USBPLUG_BYTES = 87876
USBPLUG_SHA256 = "5e36a42499c4f9568234f076214d70c5e9cd047171a2262ad85c746cd76da743"
PATCHED_USBPLUG_SHA256 = "40cc47bd829878f8ad9bcfc60f712ea3bd50f6f3886f01b9b693fd8e89d5f339"
USBPLUG_OFFSET = 14666
USBPLUG_PADDED_BYTES = 88064
PATCH_OFFSET = 0x11BCC
NEW_READ_LIMIT_SECTORS = 0x02000000
SECTOR_BYTES = 512
RC4_FORMAT_KEY = bytes.fromhex("7c4e0304550509072d2c7b38170d1711")


class PackageError(ValueError):
    """Input or output differs from the one explicitly audited package."""


def require(condition: bool, message: str) -> None:
    # Deliberately not `assert`: Python -O must not disable validation.
    if not condition:
        raise PackageError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rc4_format(data: bytes) -> bytes:
    """Rockchip BOOT payload encoding; the fixed format key is not a credential."""
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + RC4_FORMAT_KEY[i % len(RC4_FORMAT_KEY)]) & 255
        state[i], state[j] = state[j], state[i]
    i = j = 0
    result = bytearray()
    for value in data:
        i = (i + 1) & 255
        j = (j + state[i]) & 255
        state[i], state[j] = state[j], state[i]
        result.append(value ^ state[(state[i] + state[j]) & 255])
    return bytes(result)


def rockchip_crc32(data: bytes) -> int:
    """BOOT CRC: non-reflected 0x04C10DB7, init 0, no final XOR.

    This is an independent bitwise implementation, with no copied vendor table.
    The polynomial is intentionally NOT the usual CRC-32 0x04C11DB7.
    """
    crc = 0
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C10DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
    return crc


def check_transfer_bounds(actual_sectors: int, lba: int, count: int) -> None:
    """Reusable host invariant; this tool itself performs no transfers.

    `actual_sectors` must come from the freshly identified physical device.
    The patched software limit must never be substituted for real capacity.
    """
    require(all(type(v) is int for v in (actual_sectors, lba, count)), "Integer bounds required")
    require(0 < actual_sectors <= NEW_READ_LIMIT_SECTORS, "Unsupported physical capacity")
    require(0 <= lba < actual_sectors, "LBA outside physical device")
    require(0 < count <= 0xFFFF, "Invalid protocol transfer length")
    # Subtraction also works in fixed-width host implementations without lba+count overflow.
    require(count <= actual_sectors - lba, "Transfer exceeds physical device capacity")


def verify_structure(data: bytes) -> list[dict]:
    require(len(data) == SOURCE_BYTES and data[:4] == b"BOOT", "Wrong BOOT size/signature")
    require(struct.unpack_from("<H", data, 4)[0] == 102, "Wrong header size")
    require(data[43:45] == b"\0\0", "Unexpected package flags")
    require(rockchip_crc32(data[:-4]) == struct.unpack_from("<I", data, len(data)-4)[0],
            "Invalid Rockchip BOOT CRC")
    groups = ((25, 1, 102), (31, 1, 159), (37, 2, 216))
    expected = (
        (1, "rk3288_ddr_400MHz_v1", 330, 14336, 1),
        (2, "rk3288_usbplug_v2", 14666, 88064, 0),
        (4, "FlashData", 102730, 14336, 0),
        (4, "FlashBoot", 117066, 92160, 0),
    )
    entries = []
    ranges = [(0, 102)]
    for position, count, table_offset in groups:
        require(data[position] == count and data[position+5] == 57 and
                struct.unpack_from("<I", data, position+1)[0] == table_offset,
                "Unexpected entry-table layout")
        ranges.append((table_offset, table_offset + count * 57))
        for index in range(count):
            size, kind, raw_name, offset, length, delay = struct.unpack_from(
                "<BI40sIII", data, table_offset + index * 57)
            name = raw_name.decode("utf-16le").rstrip("\0")
            require(size == 57 and (kind, name, offset, length, delay) == expected[len(entries)],
                    "Unexpected package entry")
            require(0 < length and offset + length <= len(data)-4, "Payload outside package")
            ranges.append((offset, offset+length))
            entries.append({"type": kind, "name": name, "offset": offset,
                            "bytes": length, "delay_ms": delay})
    ordered = sorted(ranges)
    require(all(a[1] == b[0] for a, b in zip(ordered, ordered[1:])), "Gap or overlap in package")
    require(ordered[-1][1] == len(data)-4, "Payload does not end at CRC")
    return entries


def patch_package(source: bytes) -> tuple[bytes, dict]:
    require(len(source) == SOURCE_BYTES and sha256(source) == SOURCE_SHA256,
            "Unknown input: exact audited original package SHA-256 required")
    entries = verify_structure(source)
    end = USBPLUG_OFFSET + USBPLUG_PADDED_BYTES
    decoded = rc4_format(source[USBPLUG_OFFSET:end])
    require(sha256(decoded[:USBPLUG_BYTES]) == USBPLUG_SHA256, "Unexpected decoded usbplug")
    require(decoded[USBPLUG_BYTES:] == bytes(USBPLUG_PADDED_BYTES-USBPLUG_BYTES),
            "Unexpected usbplug padding")
    require(decoded[0x11BBC:0x11BD4] == bytes.fromhex(
        "f6484ff400520021c0e905125200c2619200c0e903217047"), "Instruction fingerprint mismatch")
    patched = bytearray(decoded)
    patched[PATCH_OFFSET:PATCH_OFFSET+2] = bytes.fromhex("d202")
    require([i for i, (old, new) in enumerate(zip(decoded, patched)) if old != new] ==
            [PATCH_OFFSET, PATCH_OFFSET+1], "Plaintext mutation outside the two patch bytes")
    require(sha256(patched[:USBPLUG_BYTES]) == PATCHED_USBPLUG_SHA256, "Wrong patched usbplug")
    result = bytearray(source)
    result[USBPLUG_OFFSET:end] = rc4_format(patched)
    struct.pack_into("<I", result, len(result)-4, rockchip_crc32(result[:-4]))
    changed = [i for i, (old, new) in enumerate(zip(source, result)) if old != new]
    allowed = [USBPLUG_OFFSET+PATCH_OFFSET, USBPLUG_OFFSET+PATCH_OFFSET+1,
               *range(len(result)-4, len(result))]
    require(changed == allowed, "Package mutation outside payload instruction and trailing CRC")
    require(result[:USBPLUG_OFFSET] == source[:USBPLUG_OFFSET] and
            result[end:-4] == source[end:-4], "Unrelated package data changed")
    require(rc4_format(result[USBPLUG_OFFSET:end]) == patched, "RC4 round-trip mismatch")
    require(verify_structure(result) == entries, "Package structure changed")
    require(sha256(result) == OUTPUT_SHA256, "Unexpected final package SHA-256")
    report = {
        "status": "offline_verified_only", "hardware_access": False,
        "ram_download_only": True, "never_flash_as_emmc_boot_or_system_image": True,
        "input_sha256": SOURCE_SHA256, "output_sha256": OUTPUT_SHA256,
        "bytes": len(result), "plaintext_changed_bytes": 2,
        "package_changed_offsets_hex": [hex(v) for v in changed],
        "old_crc": "0x6febd791", "new_crc": "0x2165100a",
        "old_read_limit_sectors": 0x10000,
        "new_read_limit_sectors": NEW_READ_LIMIT_SECTORS,
        "sector_bytes": SECTOR_BYTES,
        "real_physical_capacity_must_be_checked_separately": True,
        "header_entries_ddr_flashdata_flashboot_unchanged": True,
    }
    return bytes(result), report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Exact original BOOT package")
    parser.add_argument("--output", type=Path, required=True, help="New filename ending RAM-ONLY.bin")
    args = parser.parse_args()
    try:
        require(args.input.is_file() and args.input.stat().st_size == SOURCE_BYTES,
                "Input must be the original regular package file")
        require(args.output.name.endswith("RAM-ONLY.bin"), "Output name must end RAM-ONLY.bin")
        manifest = args.output.with_suffix(".manifest.json")
        require(args.output.resolve() != args.input.resolve(), "Input and output must differ")
        require(not args.output.exists() and not args.output.is_symlink() and
                not manifest.exists() and not manifest.is_symlink(), "Output/report already exists")
        result, report = patch_package(args.input.read_bytes())
        with args.output.open("xb") as target:
            target.write(result)
        with manifest.open("x", encoding="utf-8", newline="\n") as target:
            json.dump(report, target, indent=2)
            target.write("\n")
        print(json.dumps(report, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(2, "Refused: " + str(error) + "\n")


if __name__ == "__main__":
    main()
