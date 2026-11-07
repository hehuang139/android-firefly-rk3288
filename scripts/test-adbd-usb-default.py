#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the fixed-tag adbd patch and installer in isolated temporary trees."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


BASE = "9084198a2d4b0f6a0f174260fb42da33485b684d"


def run(command, **kwargs):
    return subprocess.run(command, text=True, capture_output=True, check=True, **kwargs)


def selection(source):
    start = source.index("#if defined(__ANDROID__)\n    if (access(USB_FFS_ADB_EP0")
    end = source.index('    LOG(INFO) << "adbd started";', start)
    # The pre-patch selector also reads this variable, declared just before the block.
    prefix = "bool is_usb = false;\n" if "is_usb = true" in source[start:end] else ""
    return prefix + source[start:end]


def harness(source, fixed):
    header = r'''
#include <cassert>
#include <cstdio>
#include <map>
#include <string>
#include <vector>
#define __ANDROID__ 1
#define USB_FFS_ADB_EP0 "/dev/usb-ffs/adb/ep0"
#define F_OK 0
#define DEFAULT_ADB_LOCAL_TRANSPORT_PORT 5555
#define D(...) ((void)0)
static bool endpoint_present;
static int usb_calls;
static std::map<std::string, std::string> properties;
static std::vector<std::string> listeners;
int access(const char*, int) { return endpoint_present ? 0 : -1; }
void usb_init() { ++usb_calls; }
void setup_adb(const std::vector<std::string>& addrs) { listeners = addrs; }
namespace android { namespace base {
std::string GetProperty(const std::string& key, const std::string& fallback) {
    auto it = properties.find(key);
    return it == properties.end() ? fallback : it->second;
}
std::string StringPrintf(const char* format, int port) {
    char buffer[80];
    std::snprintf(buffer, sizeof(buffer), format, port);
    return buffer;
}
std::vector<std::string> Split(const std::string& value, const std::string& delim) {
    std::vector<std::string> result;
    size_t start = 0, end;
    while ((end = value.find(delim, start)) != std::string::npos) {
        result.push_back(value.substr(start, end - start));
        start = end + delim.size();
    }
    result.push_back(value.substr(start));
    return result;
}
}}
void select_transports() {
'''
    footer = r'''
}
void check(bool ep0, std::map<std::string, std::string> props,
           std::vector<std::string> expected) {
    endpoint_present = ep0; properties = props; listeners.clear(); usb_calls = 0;
    select_transports();
    assert(usb_calls == (ep0 ? 1 : 0));
    assert(listeners == expected);
}
int main() {
    const std::vector<std::string> fallback = FIXED ? std::vector<std::string>{}
        : std::vector<std::string>{"tcp:5555", "vsock:5555"};
    check(false, {}, fallback);
    check(false, {{"service.adb.tcp.port", "-1"}}, fallback);
    check(false, {{"service.adb.tcp.port", "0"}}, fallback);
    check(false, {{"service.adb.tcp.port", "invalid"}}, fallback);
    check(true, {}, {});
    check(true, {{"service.adb.tcp.port", "-1"}}, {});
    check(false, {{"service.adb.tcp.port", "6000"}}, {"tcp:6000", "vsock:6000"});
    check(true, {{"service.adb.tcp.port", "6000"}}, {"tcp:6000", "vsock:6000"});
    check(false, {{"persist.adb.tcp.port", "6001"}}, {"tcp:6001", "vsock:6001"});
    check(false, {{"service.adb.tcp.port", "-1"}, {"persist.adb.tcp.port", "6001"}}, fallback);
    check(false, {{"service.adb.listen_addrs", "localabstract:explicit-adb"}},
          {"localabstract:explicit-adb"});
    check(false, {{"service.adb.listen_addrs", "tcp:6002,vsock:6002"},
                  {"service.adb.tcp.port", "6000"}}, {"tcp:6002", "vsock:6002"});
    std::puts("12 transport-selection cases passed");
}
'''.replace("FIXED", "true" if fixed else "false")
    return header + selection(source) + footer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aosp", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    module = args.aosp.resolve() / "packages/modules/adb"
    original = run(["git", "show", BASE + ":daemon/main.cpp"], cwd=module).stdout
    with tempfile.TemporaryDirectory(prefix="firefly-adbd-usb-test-") as temporary:
        fixture = Path(temporary) / "aosp"
        fixture_module = fixture / "packages/modules/adb"
        fixture_module.parent.mkdir(parents=True)
        run(["git", "clone", "--shared", "--no-checkout", "--quiet",
             str(module), str(fixture_module)])
        # Point only the isolated clone at the known source commit.
        run(["git", "checkout", BASE, "--", "daemon/main.cpp"],
            cwd=fixture_module)
        run(["git", "update-ref", "--no-deref", "HEAD", BASE], cwd=fixture_module)
        (fixture / ".repo").mkdir()
        (fixture / ".repo/manifest.xml").write_text("<manifest/>\n")
        install = [sys.executable, str(source / "scripts/install-port.py"), str(fixture)]
        first = run(install)
        assert "Applied adbd USB-only default patch:" in first.stdout
        patched = (fixture_module / "daemon/main.cpp").read_text()
        second = run(install)
        assert "already applied:" in second.stdout
        assert (fixture_module / "daemon/main.cpp").read_text() == patched
        assert (fixture / "device/firefly/rk3288/.firefly-port").is_file()
        assert (fixture / "device/firefly/rk3288/init/init.fireflyrk3288.rc").read_bytes() == (
            source / "device/firefly/rk3288/init/init.fireflyrk3288.rc").read_bytes()
        auth_end = original.index("    bool is_usb = false;")
        assert original[:auth_end] == patched[:auth_end]
        tail = '    LOG(INFO) << "adbd started";'
        assert original[original.index(tail):] == patched[patched.index(tail):]
        for label, text, fixed in (("baseline", original, False), ("patched", patched, True)):
            cpp = Path(temporary) / (label + ".cpp")
            binary = Path(temporary) / label
            cpp.write_text(harness(text, fixed))
            run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(binary)])
            run([str(binary)])
        conflict = original.replace("std::vector<std::string> addrs;",
                                    "std::vector<std::string> conflicting_local_edit;", 1)
        (fixture_module / "daemon/main.cpp").write_text(conflict)
        rejected = subprocess.run(install, text=True, capture_output=True)
        assert rejected.returncode != 0 and "neither the clean base" in rejected.stderr
        assert (fixture_module / "daemon/main.cpp").read_text() == conflict
        other_commit = run(["git", "-c", "user.name=Port test", "-c",
                            "user.email=port-test@example.invalid", "commit-tree",
                            BASE + "^{tree}", "-m", "Isolated wrong-HEAD fixture"],
                           cwd=fixture_module).stdout.strip()
        run(["git", "update-ref", "--no-deref", "HEAD", other_commit], cwd=fixture_module)
        wrong_head = subprocess.run(install, text=True, capture_output=True)
        assert wrong_head.returncode != 0 and "requires android-17.0.0_r1" in wrong_head.stderr
    result = {
        "base_commit": BASE,
        "baseline_main_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "patched_main_sha256": hashlib.sha256(patched.encode()).hexdigest(),
        "patch_sha256": hashlib.sha256((source / "patches/0001-adbd-disable-implicit-network-fallback.patch").read_bytes()).hexdigest(),
        "installer_cases": ["first application", "idempotent repeat", "conflict rejected without overwriting", "wrong HEAD rejected"],
        "transport_cases_per_source": 12,
        "transport_source": "actual main.cpp USB/listener selection block; properties, ep0 access and side effects substituted by host stubs",
        "baseline_missing_ep0_default": ["tcp:5555", "vsock:5555"],
        "patched_missing_ep0_default": [],
        "usb_setup_and_explicit_address_port_cases": "passed",
        "auth_prefix_and_post_selection_source_unchanged": True,
        "scope": "isolated Git fixtures and host C++ source-block execution",
    }
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
