#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify one XZ image against its assembly manifest, without extracting it.

Only ordinary input files are read. The JSON report is created exclusively;
an existing report is never overwritten. Python 3.10 and later are supported.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import lzma
from pathlib import Path
import platform
import re
import stat
import sys

BLOCK = 4 * 1024 * 1024
CHECKS = {lzma.CHECK_CRC32: "CRC32", lzma.CHECK_CRC64: "CRC64",
          lzma.CHECK_SHA256: "SHA256"}


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Input is not an ordinary file: " + str(path))
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def verify(image, manifest, report):
    image_before = identity(image)
    manifest_before = identity(manifest)
    manifest_bytes = manifest.read_bytes()
    source = json.loads(manifest_bytes)
    expected_size = source["image_size"]
    expected_sha = source["image_sha256"]
    if type(expected_size) is not int or expected_size <= 0:
        raise ValueError("Manifest image_size must be a positive integer")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ValueError("Manifest image_sha256 must be a lowercase SHA256 digest")
    report["manifest"] = {"path": str(manifest), "size": len(manifest_bytes),
                          "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                          "image_size": expected_size,
                          "image_sha256": expected_sha,
                          "boot_medium": source.get("boot_medium")}
    compressed = hashlib.sha256()
    uncompressed = hashlib.sha256()
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ)
    compressed_size = 0
    size = 0
    with image.open("rb") as stream:
        for block in iter(lambda: stream.read(BLOCK), b""):
            compressed.update(block)
            compressed_size += len(block)
            if decoder.eof:
                raise ValueError("Data follows the end of the XZ stream")
            pending = block
            while pending or not decoder.needs_input:
                output = decoder.decompress(pending, max_length=BLOCK)
                pending = b""
                size += len(output)
                uncompressed.update(output)
                if size > expected_size:
                    raise ValueError("Uncompressed image exceeds manifest image_size")
                if decoder.eof:
                    if decoder.unused_data:
                        raise ValueError("Data follows the end of the XZ stream")
                    break
    if not decoder.eof:
        raise ValueError("Truncated XZ stream")
    if decoder.check not in CHECKS or not lzma.is_check_supported(decoder.check):
        raise ValueError("XZ stream requires a supported integrity check")
    if size != expected_size:
        raise ValueError("Uncompressed image size does not match assembly manifest")
    if uncompressed.hexdigest() != expected_sha:
        raise ValueError("Uncompressed SHA256 does not match assembly manifest")
    if image_before != identity(image) or manifest_before != identity(manifest):
        raise ValueError("Input changed during verification")
    report.update({
        "image": {"path": str(image), "size": compressed_size,
                  "sha256": compressed.hexdigest()},
        "uncompressed": {"size": size, "sha256": uncompressed.hexdigest()},
        "xz_integrity_check": CHECKS[decoder.check],
        "checks": {"complete_xz_stream": True, "xz_integrity": True,
                   "no_trailing_data": True, "uncompressed_size": True,
                   "uncompressed_sha256": True, "inputs_unchanged": True},
        "passed": True,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.report.exists() or args.report.is_symlink():
        parser.error("Report already exists: " + str(args.report))
    report = {"format": 1, "started_at": now(), "python": platform.python_version(),
              "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "passed": False}
    try:
        verify(args.image.resolve(strict=True), args.manifest.resolve(strict=True), report)
    except (OSError, ValueError, KeyError, TypeError, lzma.LZMAError) as error:
        report["error"] = str(error)
    report["finished_at"] = now()
    with args.report.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
