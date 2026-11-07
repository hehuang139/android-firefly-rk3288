#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the system-init bootstrap linker exception using actual ext4 members."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-image", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    script = Path(__file__).resolve()
    verifier = script.with_name("verify-sd.py")
    spec = importlib.util.spec_from_file_location("elf_interp_verify", verifier)
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    cases = []

    def accepts(name, binary, installed_path=None):
        result = verify.elf_info(binary, installed_path=installed_path)
        cases.append({"name": name, "passed": True, "elf": result})

    def rejects(name, binary, installed_path=None):
        try:
            verify.elf_info(binary, installed_path=installed_path)
        except verify.VerificationError as error:
            cases.append({"name": name, "passed": True, "rejection": str(error)})
        else:
            raise AssertionError("Expected rejection: " + name)

    with tempfile.TemporaryDirectory(prefix="firefly-elf-interpreter-") as temporary:
        scratch = Path(temporary)
        filesystem = verify.Ext4(args.system_image, scratch, None)
        real, binary = filesystem.dump("/system/bin/init")
        linker_real, linker = filesystem.dump("/system/bin/bootstrap/linker")
        assert filesystem.inode(real)["mode"] & 0o111
        assert filesystem.inode(linker_real)["mode"] & 0o111
        accepts("actual init bootstrap interpreter at exact installed path", binary, real)
        accepts("actual bootstrap linker is ARM32 without an interpreter", linker)
        assert verify.elf_info(linker)["interpreter"] is None
        rejects("bootstrap interpreter without installed init role", binary)
        rejects("bootstrap interpreter on an unrelated system executable", binary, "/system/bin/unrelated")
        rejects("bootstrap interpreter on a vendor executable", binary, "/vendor/bin/init")
        rejects("bootstrap interpreter on an unnormalized init path", binary, "/system/bin/../bin/init")
        data = bytearray(binary.read_bytes())
        header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
        for index in range(header[10]):
            ptype, offset, _, _, size, _, _, _ = struct.unpack_from("<8I", data, header[5] + index * header[9])
            if ptype == 3:
                break
        else:
            raise AssertionError("Actual init lacks PT_INTERP")

        def changed_interpreter(name, value):
            replacement = value.encode() + b"\0"
            assert len(replacement) <= size
            changed = bytearray(data)
            changed[offset:offset + size] = replacement.ljust(size, b"\0")
            destination = scratch / name
            destination.write_bytes(changed)
            return destination

        normal = changed_interpreter("normal-interpreter.fixture", "/system/bin/linker")
        accepts("standard Android interpreter remains accepted", normal)
        unknown = changed_interpreter("unknown-interpreter.fixture", "/system/bin/unknown/linker")
        rejects("unknown interpreter rejected for init", unknown, real)
        rejects("unknown interpreter rejected without init role", unknown)
        wrong_arch = scratch / "wrong-arch.fixture"
        malformed = bytearray(data)
        struct.pack_into("<H", malformed, 18, 183)
        wrong_arch.write_bytes(malformed)
        rejects("non-ARM32 binary rejected even with init role", wrong_arch, real)
        readelf = subprocess.run(["readelf", "-lW", str(binary)], check=True,
                                 capture_output=True, text=True)
        actual = {"system_image": str(args.system_image.resolve()), "init_path": real,
                  "init": verify.elf_info(binary, installed_path=real), "linker_path": linker_real,
                  "linker": verify.elf_info(linker), "readelf": readelf.stdout}
    report = {"result": "passed", "fixture_cases": len(cases), "cases": cases,
              "actual": actual, "verifier_sha256": hashlib.sha256(verifier.read_bytes()).hexdigest(),
              "test_sha256": hashlib.sha256(script.read_bytes()).hexdigest()}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"result": "passed", "fixture_cases": len(cases), "report": str(args.report)}))


if __name__ == "__main__":
    main()
