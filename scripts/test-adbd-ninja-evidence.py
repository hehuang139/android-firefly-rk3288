#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reproduce multi-output Ninja log semantics with the actual AOSP Ninja binary."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ninja", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("Report already exists: " + str(args.report))
    helper_path = Path(__file__).with_name("verify-adbd-apex.py")
    spec = importlib.util.spec_from_file_location("adbd_verifier", helper_path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    ninja = args.ninja.resolve(strict=True)
    report = {"passed": False, "ninja": verifier.file_record(ninja),
              "verifier": verifier.file_record(helper_path), "checks": [], "commands": []}

    def check(name, condition):
        report["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise RuntimeError(name)

    def run(arguments, directory):
        result = subprocess.run([str(arg) for arg in arguments], cwd=directory,
                                capture_output=True, text=True, check=True)
        report["commands"].append({"argv": [str(arg) for arg in arguments],
                                   "exit_code": result.returncode,
                                   "output": result.stdout + result.stderr})
        return result

    try:
        with tempfile.TemporaryDirectory(prefix="adbd-ninja-evidence-") as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_text("input\n")
            os.utime(source, ns=(9_000_000_000, 9_000_000_000))
            code = ("from pathlib import Path; import os; "
                    "[(Path(name).write_text(name), os.utime(name, ns=(stamp, stamp))) "
                    "for name, stamp in [('first',10000000000),('second',11000000000)]]")
            command = shlex.join([sys.executable, "-c", code])
            (root / "build.ninja").write_text(
                "rule make\n  command = " + command +
                "\n  restat = 1\nbuild first | second: make source\n")
            report["ninja_version"] = run([ninja, "--version"], root).stdout.strip()
            run([ninja, "-f", "build.ninja"], root)
            outputs = {name: verifier.file_record(root / name) for name in ("first", "second")}
            entries = verifier.ninja_log_records(root / ".ninja_log", set(outputs))
            rule = {"outputs": ["first", "second"]}
            report["actual_multi_output"] = {"files": outputs, "records": entries}
            check("actual-ninja-logs-edge-maximum-for-explicit-and-implicit-output",
                  {entry["output_mtime_ns"] for entry in entries.values()} == {11_000_000_000})
            check("different-per-file-mtimes-accepted-only-with-exact-edge-maximum",
                  verifier.edge_log_evidence(rule, outputs, entries)[0])
            changed = copy.deepcopy(entries)
            changed["first"]["output_mtime_ns"] = 10_000_000_000
            check("different-peer-mtime-records-rejected",
                  not verifier.edge_log_evidence(rule, outputs, changed)[0])
            changed = copy.deepcopy(entries)
            changed["second"]["command_hash"] = "different-command"
            check("different-peer-command-records-rejected",
                  not verifier.edge_log_evidence(rule, outputs, changed)[0])
            changed = copy.deepcopy(outputs)
            changed["second"]["mtime_ns"] += 1
            check("one-nanosecond-output-mismatch-rejected",
                  not verifier.edge_log_evidence(rule, changed, entries)[0])
            missing = root / "missing-peer.log"
            lines = (root / ".ninja_log").read_text().splitlines()
            missing.write_text("\n".join(line for line in lines if "\tsecond\t" not in line) + "\n")
            try:
                verifier.ninja_log_records(missing, set(outputs))
            except verifier.VerificationError:
                check("missing-implicit-output-success-record-rejected", True)
            else:
                check("missing-implicit-output-success-record-rejected", False)
            os.utime(source, ns=(12_000_000_000, 12_000_000_000))
            run([ninja, "-f", "build.ninja"], root)
            restat_entries = verifier.ninja_log_records(root / ".ninja_log", set(outputs))
            report["actual_unchanged_restat_records"] = restat_entries
            check("actual-unchanged-restat-logs-newest-input",
                  {entry["output_mtime_ns"] for entry in restat_entries.values()} == {12_000_000_000})
            check("restat-without-exact-output-maximum-is-rejected",
                  not verifier.edge_log_evidence(rule, outputs, restat_entries)[0])
        report["passed"] = True
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError,
            verifier.VerificationError) as error:
        report["error"] = str(error)
    with args.report.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": report["passed"], "report": str(args.report),
                      "error": report.get("error")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
