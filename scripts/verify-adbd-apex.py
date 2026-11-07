#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the patched ARM adbd in an actual system CAPEX against build evidence.

The AOSP tree is read-only. --capex may be a file extracted from system.img;
its name does not matter. Extraction uses the built AOSP deapexer without
mounting filesystems. --scratch-dir is an existing parent directory; a new
private child directory retains the extracted files for inspection.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import mmap
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile


BASE_COMMIT = "9084198a2d4b0f6a0f174260fb42da33485b684d"
PATCHED_MAIN_SHA256 = "6fdaea75b9254714df5f1529e454d399fb9e5c20f30318fc7afd06fc475433b2"
MAIN = "packages/modules/adb/daemon/main.cpp"
ADBD = "out/soong/.intermediates/packages/modules/adb/adbd/android_arm_armv7-a-neon_cortex-a15_apex31/"
APEX = "out/soong/.intermediates/packages/modules/adb/apex/com.android.adbd/android_common_com.android.adbd/"
PATHS = {
    "main": MAIN,
    "object": ADBD + "obj/packages/modules/adb/daemon/main.o",
    "linked": ADBD + "unstripped/adbd",
    "binary": ADBD + "adbd",
    "staging_binary": APEX + "image.apex/bin/adbd",
    "apex_unsigned": APEX + "com.android.adbd.apex.unsigned",
    "apex": APEX + "com.android.adbd.apex",
    "capex_unsigned": APEX + "com.android.adbd.capex.unsigned",
    "built_capex": APEX + "com.android.adbd.capex",
    "installed_capex": "out/target/product/rk3288/system/apex/com.android.adbd.capex",
}
RULE_EDGES = (
    ("object", MAIN), ("linked", PATHS["object"]),
    ("binary", PATHS["linked"]), ("apex_unsigned", PATHS["binary"]),
    ("apex", PATHS["apex_unsigned"]), ("capex_unsigned", PATHS["apex"]),
    ("built_capex", PATHS["capex_unsigned"]),
    ("installed_capex", PATHS["built_capex"]),
)
LOGGED = ("object", "linked", "binary", "apex_unsigned", "apex",
          "capex_unsigned", "built_capex", "installed_capex")


class VerificationError(Exception):
    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report or {}


def identity(path):
    info = path.stat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def ordinary(path):
    try:
        resolved = Path(path).resolve(strict=True)
    except FileNotFoundError as error:
        raise VerificationError("Required file is missing: " + str(path)) from error
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise VerificationError("Required input is not an ordinary file: " + str(path))
    return resolved


def file_record(path):
    path = ordinary(path)
    before = identity(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    if before != identity(path):
        raise VerificationError("Input changed while hashing: " + str(path))
    return {"path": str(path), "size": before[2], "mtime_ns": before[3],
            "sha256": digest.hexdigest()}


def executable(candidates):
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return ordinary(candidate)
    raise VerificationError("Required executable is missing: " +
                            ", ".join(str(p) for p in candidates if p))


def command(arguments, cwd=None, env=None):
    result = subprocess.run([str(arg) for arg in arguments], cwd=cwd, env=env,
                            capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise VerificationError("Command failed: " + " ".join(str(a) for a in arguments)
                                + "\n" + (result.stdout + result.stderr)[-6000:])
    return {"argv": [str(a) for a in arguments], "exit_code": result.returncode,
            "output": (result.stdout + result.stderr)[-6000:]}


def ninja_log_records(path, wanted):
    """Read successful Ninja v5 output records, retaining the last for each output."""
    records = {}
    with path.open() as stream:
        if stream.readline().strip() != "# ninja log v5":
            raise VerificationError("Unsupported Ninja log header: " + str(path))
        for line_number, line in enumerate(stream, 2):
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 5 or fields[3] not in wanted:
                continue
            try:
                start, end, mtime = map(int, fields[:3])
                int(fields[4], 16)
            except ValueError as error:
                raise VerificationError("Invalid Ninja success record at line " + str(line_number)) from error
            if start < 0 or end < start or mtime <= 0:
                raise VerificationError("Invalid Ninja success timing at line " + str(line_number))
            records[fields[3]] = {"line": line_number, "start_ms": start, "end_ms": end,
                                  "output_mtime_ns": mtime, "command_hash": fields[4],
                                  "raw": line.rstrip("\n")}
    missing = wanted - records.keys()
    if missing:
        raise VerificationError("Missing Ninja success records: " + ", ".join(sorted(missing)))
    return records


def find_rules(aosp, targets):
    """Read fixed-product generated rules; no Ninja invocation or graph regeneration."""
    rules = {}
    # Search the current fixed-product shards first, then discover any moved
    # definitions in other shards. Byte searches avoid parsing gigabytes of
    # unrelated compiler flags and dependency continuations in Python.
    preferred = [aosp / "out/soong/build.aosp_firefly_rk3288.2.ninja",
                 aosp / "out/soong/build.aosp_firefly_rk3288.4.ninja",
                 aosp / "out/build-aosp_firefly_rk3288.ninja"]
    graphs = preferred + [path for path in sorted((aosp / "out/soong").glob(
        "build.aosp_firefly_rk3288*.ninja")) if path not in preferred]
    for graph in graphs:
        if not graph.is_file() or not graph.stat().st_size:
            continue
        graph_before = identity(graph)
        with graph.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            for target in sorted(targets - rules.keys()):
                marker = target.encode()
                position = mapped.find(marker, 0)
                while position != -1:
                    start = mapped.rfind(b"\nbuild ", 0, position)
                    start = start + 1 if start >= 0 else 0
                    mapped.seek(start)
                    chunks = []
                    while True:
                        line = mapped.readline()
                        if not line:
                            raise VerificationError("Truncated Ninja statement: " + str(graph))
                        continued = line.rstrip().endswith(b"$")
                        chunks.append(line.rstrip()[:-1] if continued else line.strip())
                        if not continued:
                            break
                    logical = b" ".join(chunks).decode()
                    output_text, separator, inputs = logical[6:].partition(": ")
                    if logical.startswith("build ") and separator and target in output_text.split():
                        tokens = inputs.split()
                        if not tokens:
                            raise VerificationError("Missing Ninja rule: " + target)
                        rules[target] = {"graph": str(graph.relative_to(aosp)), "byte_offset": start,
                                         "rule": tokens[0], "inputs": tokens[1:],
                                         "outputs": [output for output in output_text.split()
                                                     if output != "|"],
                                         "graph_identity": graph_before,
                                         "build_statement_sha256": hashlib.sha256(logical.encode()).hexdigest()}
                        break
                    position = mapped.find(marker, position + len(marker))
        if graph_before != identity(graph):
            raise VerificationError("Ninja graph changed while reading: " + str(graph))
        if rules.keys() >= targets:
            break
    missing = targets - rules.keys()
    if missing:
        raise VerificationError("Required Ninja rules are missing: " + ", ".join(sorted(missing)))
    return rules


def edge_log_evidence(rule, output_records, entries):
    """Check the shared Ninja success record against every actual edge output.

    Ninja records the newest output mtime for the entire command, including
    implicit outputs, and writes that same command record for every output.
    Restat records that do not equal the actual newest output are rejected;
    no time tolerance or guessed restat timestamp is accepted.
    """
    outputs = rule["outputs"]
    signatures = {tuple(entries[output][key] for key in (
        "start_ms", "end_ms", "output_mtime_ns", "command_hash")) for output in outputs}
    actual_mtimes = {output: output_records[output]["mtime_ns"] for output in outputs}
    logged_mtimes = {output: entries[output]["output_mtime_ns"] for output in outputs}
    maximum = max(actual_mtimes.values())
    passed = len(signatures) == 1 and set(logged_mtimes.values()) == {maximum}
    return passed, {"actual_output_mtimes_ns": actual_mtimes,
                    "logged_output_mtimes_ns": logged_mtimes,
                    "maximum_actual_output_mtime_ns": maximum,
                    "peer_command_records_match": len(signatures) == 1,
                    "mtime_rule": "exact maximum across all explicit and implicit outputs"}


def arm_binary(path):
    with path.open("rb") as stream:
        data = stream.read(20)
    if len(data) != 20 or data[:6] != b"\x7fELF\x01\x01":
        raise VerificationError("adbd is not a little-endian ELF32 binary: " + str(path))
    elf_type, machine = struct.unpack_from("<HH", data, 16)
    if machine != 40 or elf_type not in (2, 3):
        raise VerificationError("adbd is not an ARM executable: " + str(path))
    return {"class": "ELF32", "machine": "ARM", "type": elf_type}


def verify_adbd_apex(aosp, capex, scratch_dir):
    """Return a passed=True evidence report, or raise VerificationError with .report."""
    report = {"format": 1, "passed": False,
              "scope": "actual system CAPEX adbd bytes and fixed-source build evidence",
              "started_at": datetime.now(timezone.utc).isoformat(), "checks": []}

    def check(name, condition, detail=None):
        report["checks"].append({"name": name, "passed": bool(condition), "detail": detail})
        if not condition:
            raise VerificationError(name, report)

    try:
        aosp = Path(aosp).resolve(strict=True)
        scratch_dir = Path(scratch_dir).resolve(strict=True)
        check("scratch-parent-is-directory", scratch_dir.is_dir(), str(scratch_dir))
        paths = {name: ordinary(aosp / relative) for name, relative in PATHS.items()}
        paths["input_capex"] = ordinary(capex)
        initial = {name: identity(path) for name, path in paths.items()}
        report["aosp"] = str(aosp)
        report["files"] = {name: file_record(path) for name, path in paths.items()}
        check("main-is-fixed-patched-source",
              report["files"]["main"]["sha256"] == PATCHED_MAIN_SHA256,
              {"expected_sha256": PATCHED_MAIN_SHA256, "actual": report["files"]["main"]})
        revision = command(["git", "rev-parse", "HEAD"], cwd=aosp / "packages/modules/adb")
        report["adb_revision"] = revision
        check("adb-base-is-android17-r1", revision["output"].strip() == BASE_COMMIT, BASE_COMMIT)
        for newer, older in (("object", "main"), ("linked", "object"), ("binary", "linked")):
            check(newer + "-not-older-than-" + older,
                  report["files"][newer]["mtime_ns"] >= report["files"][older]["mtime_ns"])

        targets = {PATHS[name] for name, _ in RULE_EDGES}
        rules = find_rules(aosp, targets)
        report["ninja_rules"] = {}
        graph_initial = {}
        for name, dependency in RULE_EDGES:
            rule = rules[PATHS[name]]
            report["ninja_rules"][name] = {k: v for k, v in rule.items() if k != "inputs"}
            graph_initial[aosp / rule["graph"]] = rule["graph_identity"]
            check("ninja-dependency:" + name, dependency in rule["inputs"],
                  {"target": PATHS[name], "required_input": dependency})
        all_outputs = {output for rule in rules.values() for output in rule["outputs"]}
        output_paths = {output: ordinary(aosp / output) for output in all_outputs}
        output_initial = {output: identity(path) for output, path in output_paths.items()}
        report["ninja_edge_outputs"] = {output: file_record(path)
                                         for output, path in sorted(output_paths.items())}
        log = ordinary(aosp / "out/.ninja_log")
        log_before = identity(log)
        report["ninja_log"] = {**file_record(log), "records": {}}
        entries = ninja_log_records(log, all_outputs)
        report["ninja_log"]["edge_output_records"] = entries
        for name in LOGGED:
            entry = entries[PATHS[name]]
            report["ninja_log"]["records"][name] = entry
            passed, evidence = edge_log_evidence(rules[PATHS[name]],
                                                report["ninja_edge_outputs"], entries)
            check("ninja-success-mtime:" + name, passed, evidence)

        capex_hashes = {name: report["files"][name]["sha256"]
                        for name in ("input_capex", "built_capex", "installed_capex")}
        check("actual-capex-matches-built-and-installed", len(set(capex_hashes.values())) == 1, capex_hashes)
        with zipfile.ZipFile(paths["input_capex"]) as archive:
            check("input-is-compressed-apex", "original_apex" in archive.namelist()
                  and "apex_payload.img" not in archive.namelist())
        host_bin = aosp / "out/host/linux-x86/bin"
        tools = {
            "deapexer": executable([host_bin / "deapexer"]),
            "debugfs": executable([host_bin / "debugfs_static", host_bin / "debugfs", shutil.which("debugfs")]),
            "fsck_erofs": executable([host_bin / "fsck.erofs", shutil.which("fsck.erofs")]),
        }
        report["tools"] = {name: file_record(path) for name, path in tools.items()}
        private = Path(tempfile.mkdtemp(prefix="adbd-apex-", dir=scratch_dir))
        extracted = private / "extracted"
        report["scratch"] = str(private)
        environment = os.environ.copy()
        environment["TMPDIR"] = str(private)
        report["extraction"] = command([
            tools["deapexer"], "--debugfs_path", tools["debugfs"],
            "--fsckerofs_path", tools["fsck_erofs"], "extract", paths["input_capex"], extracted,
        ], env=environment)
        extracted_binary = ordinary(extracted / "bin/adbd")
        report["files"]["extracted_binary"] = file_record(extracted_binary)
        report["elf"] = arm_binary(extracted_binary)
        hashes = {name: report["files"][name]["sha256"]
                  for name in ("extracted_binary", "binary", "staging_binary")}
        check("actual-apex-adbd-matches-built-and-staging", len(set(hashes.values())) == 1, hashes)
        for name, path in paths.items():
            check("input-unchanged:" + name, initial[name] == identity(path))
        for output, path in output_paths.items():
            check("ninja-edge-output-unchanged:" + output,
                  output_initial[output] == identity(path))
        for graph, before in graph_initial.items():
            check("ninja-graph-unchanged:" + str(graph.relative_to(aosp)),
                  before == identity(graph))
        check("ninja-log-unchanged-during-verification", log_before == identity(log))
        report["passed"] = True
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        return report
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile, VerificationError) as error:
        report["error"] = str(error)
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        raise VerificationError(str(error), report) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aosp", type=Path, required=True)
    parser.add_argument("--capex", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True, help="New JSON report; existing files are preserved")
    parser.add_argument("--scratch-dir", type=Path, required=True, help="Existing scratch parent directory")
    args = parser.parse_args()
    if args.report.exists():
        parser.error("Report already exists: " + str(args.report))
    try:
        result = verify_adbd_apex(args.aosp, args.capex, args.scratch_dir)
    except VerificationError as error:
        result = error.report
    try:
        with args.report.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    except OSError as error:
        print("Cannot save adbd verification report: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"passed": result.get("passed", False), "report": str(args.report),
                      "error": result.get("error")}, ensure_ascii=False))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
