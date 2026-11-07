#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the ramdisk cpio parser and optionally inspect an actual gzip ramdisk."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile


def member(name, payload=b"", *, magic=b"070701", **changes):
    name = name.encode() + b"\0"
    fields = {"ino": 1, "mode": stat.S_IFDIR | 0o755, "uid": 0, "gid": 0,
              "nlink": 1, "mtime": 0, "size": len(payload), "devmajor": 0,
              "devminor": 0, "rdevmajor": 0, "rdevminor": 0,
              "namesize": len(name), "check": sum(payload) if magic == b"070702" else 0}
    fields.update(changes)
    data = magic + b"".join(f"{value:08x}".encode() for value in fields.values()) + name
    data += b"\0" * (-len(data) % 4) + payload
    return data + b"\0" * (-len(data) % 4)


def archive(*members):
    return b"".join(members) + member("TRAILER!!!")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ramdisk", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    script = Path(__file__).resolve()
    verifier = script.with_name("verify-sd.py")
    spec = importlib.util.spec_from_file_location("cpio_verify", verifier)
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    cases = []

    def accepts(name, data, expected_duplicates):
        repeats = []
        entries = verify.parse_cpio(data, duplicate_directories=repeats)
        assert repeats == expected_duplicates, (name, repeats)
        cases.append({"name": name, "passed": True, "members": len(entries),
                      "identical_empty_directory_repetitions": repeats})

    def rejects(name, data):
        try:
            verify.parse_cpio(data)
        except verify.VerificationError as error:
            cases.append({"name": name, "passed": True, "rejection": str(error)})
        else:
            raise AssertionError("Expected rejection: " + name)

    directory = member("dev")
    accepts("single empty directory", archive(directory), [])
    accepts("identical empty directory with a different inode", archive(directory, member("dev", ino=2)), ["dev"])
    accepts("normalized identical empty directory", archive(directory, member("./dev", ino=2)), ["dev"])
    accepts("three identical empty directories", archive(directory, member("dev", ino=2), member("dev", ino=3)), ["dev", "dev"])
    accepts("CRC newc identical empty directories", archive(member("dev", magic=b"070702"), member("dev", magic=b"070702", ino=2)), ["dev"])
    for field, value in (("mode", stat.S_IFDIR | 0o700), ("uid", 1), ("gid", 1),
                         ("nlink", 2), ("mtime", 1), ("devmajor", 1),
                         ("devminor", 1), ("rdevmajor", 1), ("rdevminor", 1)):
        rejects("directory metadata conflict: " + field, archive(directory, member("dev", **{field: value})))
    rejects("duplicate directory with data", archive(member("dev", b"x"), member("dev", b"x")))
    rejects("empty directory followed by directory with data", archive(directory, member("dev", b"x")))
    rejects("directory with data followed by empty directory", archive(member("dev", b"x"), directory))
    regular = member("init", b"abc", mode=stat.S_IFREG | 0o755)
    rejects("identical duplicate regular file", archive(regular, regular))
    rejects("conflicting duplicate regular file", archive(regular, member("init", b"xyz", mode=stat.S_IFREG | 0o755)))
    rejects("directory replaced by regular file", archive(directory, member("dev", mode=stat.S_IFREG | 0o755)))
    rejects("regular file replaced by directory", archive(member("dev", mode=stat.S_IFREG | 0o755), directory))
    symlink = member("dev", b"target", mode=stat.S_IFLNK | 0o777)
    rejects("duplicate symlink", archive(symlink, symlink))
    rejects("directory replaced by symlink", archive(directory, symlink))
    rejects("symlink replaced by directory", archive(symlink, directory))
    device = member("dev", mode=stat.S_IFCHR | 0o600, rdevmajor=1, rdevminor=3)
    rejects("duplicate device node", archive(device, device))
    rejects("duplicate directory invalid newc checksum", archive(directory, member("dev", check=1)))
    rejects("duplicate directory invalid CRC checksum", archive(directory, member("dev", magic=b"070702", check=1)))
    rejects("directory parent traversal", archive(member("../dev")))
    rejects("absolute directory path", archive(member("/dev")))
    rejects("missing trailer", directory)

    report = {"result": "passed", "fixture_cases": len(cases), "cases": cases,
              "parser_sha256": hashlib.sha256(verifier.read_bytes()).hexdigest(),
              "test_sha256": hashlib.sha256(script.read_bytes()).hexdigest()}
    if args.ramdisk:
        compressed = args.ramdisk.read_bytes()
        raw = gzip.decompress(compressed)
        repeats = []
        entries = verify.parse_cpio(raw, duplicate_directories=repeats)
        init = entries["init"]
        assert stat.S_ISREG(init["mode"]) and init["mode"] & 0o111
        assert init["uid"] == init["gid"] == 0
        assert stat.S_ISREG(entries["fstab.fireflyrk3288"]["mode"])
        with tempfile.TemporaryDirectory(prefix="firefly-cpio-test-") as temporary:
            init_path = Path(temporary) / "first-stage-init"
            init_path.write_bytes(init["data"])
            elf = verify.elf_info(init_path)
        audit = verify.Audit("actual-ramdisk-fstab")
        verify.check_fstab(entries["fstab.fireflyrk3288"]["data"], audit, "actual-ramdisk-fstab")
        report["actual_ramdisk"] = {
            "path": str(args.ramdisk.resolve()), "compressed_bytes": len(compressed),
            "uncompressed_bytes": len(raw), "sha256": hashlib.sha256(compressed).hexdigest(),
            "cpio_sha256": hashlib.sha256(raw).hexdigest(), "unique_members": len(entries),
            "identical_empty_directory_repetitions": repeats,
            "first_stage_init": elf, "fstab_checks": audit.data}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": report["result"], "fixture_cases": len(cases),
                      "actual_ramdisk_checked": bool(args.ramdisk), "report": str(args.report)}))


if __name__ == "__main__":
    main()
