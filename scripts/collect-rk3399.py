#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Collect bounded, read-only first-boot evidence from one RK3399 candidate.

Does not start/stop services, grant permissions, install, reboot, or write to
the board. Use an output directory outside the public repository: network,
application and log output can contain personal information.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adb", type=Path, required=True)
    p.add_argument("--serial", required=True, help="Explicit adb serial; no default target")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error("Output directory already exists; choose a new capture name")
    adb = str(a.adb.resolve(strict=True))

    def run(command, timeout=20):
        began = time.monotonic()
        try:
            r = subprocess.run([adb, "-s", a.serial, "shell", command], capture_output=True, timeout=timeout)
            return {"exit_code": r.returncode, "elapsed_seconds": round(time.monotonic() - began, 3),
                    "stdout": r.stdout.decode("utf-8", errors="replace"),
                    "stderr": r.stderr.decode("utf-8", errors="replace")}
        except subprocess.TimeoutExpired:
            return {"exit_code": None, "elapsed_seconds": timeout, "stdout": "", "stderr": "probe timeout"}

    identity = run("getprop ro.product.device; getprop ro.hardware; uname -m")
    if identity["exit_code"] != 0 or identity["stdout"].splitlines() != ["rk3399", "fireflyrk3399", "aarch64"]:
        raise SystemExit("Target is not the RK3399 ARM64 candidate; no further probes performed. " + json.dumps(identity))
    a.output.mkdir(parents=True)
    probes = {
        "boot": "cat /proc/sys/kernel/random/boot_id; cat /proc/uptime; getprop sys.boot_completed; getprop bpf.progs_loaded; getprop init.svc.netd; getprop init.svc.surfaceflinger; getprop init.svc.zygote; getprop init.svc.zygote_secondary; cat /proc/cmdline",
        "properties": "getprop",
        "storage": "cat /proc/partitions; cat /proc/mounts; df -k; ls -l /dev/block/by-name",
        "drivers": "cat /proc/modules; ls -l /sys/bus/platform/drivers/rkvdec /sys/bus/platform/drivers/panfrost; ls -l /dev/video* /dev/media* /dev/dri/* /dev/dma_heap/*",
        "kernel-log": "dmesg",
        "android-log": "logcat -b all -d -t 4000",
        "crash-log": "logcat -b crash -d",
        "audio-devices": "cat /proc/asound/cards; cat /proc/asound/pcm; cat /proc/asound/card*/id; cat /proc/asound/card*/eld*",
        "audio-policy": "dumpsys media.audio_policy",
        "audio-flinger": "dumpsys media.audio_flinger",
        "surfaceflinger": "dumpsys SurfaceFlinger",
        "display": "dumpsys display",
        "codecs": "dumpsys media.codec; dumpsys media.metrics",
        "network": "ip -s link; ip address; ip route; dumpsys ethernet; dumpsys connectivity",
        "wifi": "cmd wifi status; dumpsys wifi",
        "input": "cat /proc/bus/input/devices; dumpsys input",
        "youtube": "cmd package list packages --show-versioncode com.google.android.youtube.tv; dumpsys package com.google.android.youtube.tv; cat /data/misc/firefly-youtube-preinstall/status",
        "launcher": "dumpsys package org.firefly.tv; dumpsys activity activities",
        "thermal-memory": "cat /proc/meminfo; cat /sys/class/thermal/thermal_zone*/type; cat /sys/class/thermal/thermal_zone*/temp; cat /sys/devices/system/cpu/online",
    }
    records = {}
    for name, command in probes.items():
        result = run(command)
        output = a.output / (name + ".json")
        output.write_text(json.dumps({"command": command, **result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records[name] = {"exit_code": result["exit_code"], "elapsed_seconds": result["elapsed_seconds"],
                         "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
        print(json.dumps({"probe": name, "exit_code": result["exit_code"]}), flush=True)
    final_boot = run("cat /proc/sys/kernel/random/boot_id; cat /proc/uptime")
    first = json.loads((a.output / "boot.json").read_text(encoding="utf-8"))
    first_lines, last_lines = first["stdout"].splitlines(), final_boot["stdout"].splitlines()
    same_boot = first["exit_code"] == 0 and final_boot["exit_code"] == 0 and len(first_lines) >= 2 and len(last_lines) >= 2 and first_lines[0] == last_lines[0]
    summary = {"format": 1, "board": "firefly,firefly-rk3399", "serial": a.serial,
               "captured_utc": datetime.now(timezone.utc).isoformat(), "identity": identity,
               "same_boot_during_capture": same_boot, "ending_boot": final_boot, "probes": records,
               "physical_audio_video_input_acceptance": "not established by log collection",
               "failed_probes": [k for k, v in records.items() if v["exit_code"] != 0]}
    (a.output / "capture.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"capture": str(a.output), "same_boot": same_boot, "failed_probes": summary["failed_probes"]}))


if __name__ == "__main__":
    main()
