# SPDX-License-Identifier: MIT
"""Exercise UDC discovery and the late-controller init binding contract on a host."""
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEVICE = ROOT / "device/firefly/rk3399"
SOURCE = DEVICE / "init/firefly-usb-controller.sh"
RC = DEVICE / "init/init.fireflyrk3399.rc"
READY = "vendor.firefly.usb.controller.ready"


@unittest.skipUnless(shutil.which("sh"), "POSIX host required")
class ControllerDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rk3399-usb-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.udcs = self.root / "sys/class/udc"
        self.udcs.mkdir(parents=True)
        self.commands = self.root / "commands"
        self.commands.mkdir()
        fake = r'''import json,os,sys
from pathlib import Path
r=Path(os.environ['USB_TEST_ROOT']); mode=os.environ['USB_TEST_MODE']
if Path(sys.argv[0]).name == 'setprop':
    with (r/'properties.jsonl').open('a') as f:
        f.write(json.dumps(sys.argv[1:])+'\n')
    if mode == 'property-failure' and sys.argv[1] == 'sys.usb.controller':
        raise SystemExit(1)
else:
    count=r/'waits'; n=int(count.read_text())+1 if count.exists() else 1
    count.write_text(str(n))
    if mode == 'delayed' and n == 14:
        target=r/'devices/platform/fe800000.usb/gadget/udc/fe800000.usb'
        target.mkdir(parents=True)
        (r/'sys/class/udc/fe800000.usb').symlink_to(target)
    if mode == 'ambiguous-then-unique' and n == 5:
        (r/'sys/class/udc/duplicate').unlink()
    if n == 20:
        raise SystemExit(99)
'''
        for name in ("setprop", "sleep"):
            command = self.commands / name
            command.write_text("#!" + sys.executable + "\n" + fake)
            command.chmod(0o755)
        self.script = self.root / "discover.sh"
        self.script.write_text(SOURCE.read_text().replace(
            "/sys/class/udc/*", str(self.udcs) + "/*"))

    def add_udc(self, name="fe800000.usb", controller="fe800000.usb"):
        target = self.root / "devices/platform" / controller / "gadget/udc" / name
        target.mkdir(parents=True)
        (self.udcs / name).symlink_to(target)

    def run_script(self, mode="normal"):
        env = dict(os.environ, USB_TEST_ROOT=str(self.root), USB_TEST_MODE=mode)
        env["PATH"] = str(self.commands) + os.pathsep + env["PATH"]
        return subprocess.run(["sh", str(self.script)], env=env,
                              capture_output=True, text=True, timeout=10)

    def properties(self):
        return [json.loads(line) for line in
                (self.root / "properties.jsonl").read_text().splitlines()]

    def test_existing_unique_controller(self):
        self.add_udc()
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.properties(), [[READY, "0"],
                         ["sys.usb.controller", "fe800000.usb"], [READY, "1"]])

    def test_controller_after_old_ten_second_deadline(self):
        self.assertEqual(self.run_script("delayed").returncode, 0)
        self.assertEqual((self.root / "waits").read_text(), "14")
        self.assertEqual(self.properties()[-1], [READY, "1"])

    def test_unrelated_controller_is_never_selected(self):
        self.add_udc("external", "unrelated.usb")
        self.assertEqual(self.run_script().returncode, 99)
        self.assertEqual(self.properties(), [[READY, "0"]])

    def test_ambiguous_controller_is_never_selected(self):
        self.add_udc()
        self.add_udc("duplicate")
        self.assertEqual(self.run_script().returncode, 99)
        self.assertEqual(self.properties(), [[READY, "0"]])

    def test_waits_for_unique_controller_after_ambiguity(self):
        self.add_udc()
        self.add_udc("duplicate")
        self.assertEqual(self.run_script("ambiguous-then-unique").returncode, 0)
        self.assertEqual((self.root / "waits").read_text(), "5")
        self.assertEqual(self.properties()[-1], [READY, "1"])

    def test_failed_controller_property_does_not_publish_ready(self):
        self.add_udc()
        self.assertEqual(self.run_script("property-failure").returncode, 1)
        self.assertNotIn([READY, "1"], self.properties())

    def test_posix_shell_syntax(self):
        self.assertEqual(subprocess.run(["sh", "-n", str(SOURCE)],
                         capture_output=True).returncode, 0)


class LateBindingTest(unittest.TestCase):
    def setUp(self):
        self.rc = RC.read_text()
        trigger = next(line for line in self.rc.splitlines()
                       if line.startswith("on property:" + READY + "=1"))
        self.conditions = dict(part.removeprefix("property:").split("=", 1)
                               for part in trigger.removeprefix("on ").split(" && "))

    def matches(self, state):
        return all(expected == "*" or state.get(name, "") == expected
                   for name, expected in self.conditions.items())

    def test_all_controller_and_functionfs_ready_orders_bind(self):
        events = [("sys.usb.controller", "fe800000.usb"), (READY, "1"),
                  ("sys.usb.config", "adb"), ("sys.usb.configfs", "1"),
                  ("sys.usb.ffs.ready", "1")]
        for ordered in itertools.permutations(events):
            # Production publishes the controller before the ready flag.
            if ordered.index(events[0]) > ordered.index(events[1]):
                continue
            state = {}
            bound = False
            for name, value in ordered:
                state[name] = value
                if self.matches(state):
                    self.assertEqual(state["sys.usb.controller"], "fe800000.usb")
                    bound = True
            self.assertTrue(bound, ordered)

    def test_does_not_bind_before_ffs_or_controller_ready(self):
        state = {"sys.usb.controller": "fe800000.usb", READY: "1",
                 "sys.usb.config": "adb", "sys.usb.configfs": "1",
                 "sys.usb.ffs.ready": "1"}
        for name in (READY, "sys.usb.configfs", "sys.usb.ffs.ready"):
            self.assertFalse(self.matches(dict(state, **{name: "0"})))
        self.assertFalse(self.matches(dict(state, **{"sys.usb.config": "none"})))

    def test_discovery_is_nonblocking_and_does_not_restart_adbd(self):
        self.assertIn("    start firefly-usb-controller\n", self.rc)
        self.assertNotIn("exec_start firefly-usb-controller", self.rc)
        self.assertNotIn("timeout_period", self.rc)
        self.assertNotIn("restart adbd", self.rc)
        self.assertNotIn("stop adbd", self.rc)
        self.assertIn("write /config/usb_gadget/g1/UDC ${sys.usb.controller}", self.rc)


if __name__ == "__main__":
    unittest.main()
