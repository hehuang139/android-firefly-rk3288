# SPDX-License-Identifier: MIT
"""Run the production shell flow in a temporary sandbox with a fake package manager."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "device/firefly/rk3399/apps/youtube-preinstall/install-youtube-tv.sh"
PACKAGE = "com.google.android.youtube.tv"
SIGNER = "21199d112cece428c82cb0df221da24ff8674c7a982a83a17a970eec43305b4a"


@unittest.skipUnless(shutil.which("bash"), "Linux/bash host required")
class FirstInstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="youtube-first-install-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = self.root / "payload"
        self.payload.mkdir()
        self.state = self.root / "state"
        self.installed = self.root / "data/app/youtube/base.apk"
        self.installed.parent.mkdir(parents=True)
        self.apk = self.payload / "YouTubeTV.apk"
        self.apk.write_bytes(b"synthetic test payload - never a real APK")
        self.digest = hashlib.sha256(self.apk.read_bytes()).hexdigest()
        self.config = self.payload / "youtube-tv.conf"
        self.config.write_text(f"sha256={self.digest}\nversion_code=42\npackage={PACKAGE}\nsigner_sha256={SIGNER}\n")
        self.control = self.root / "control.json"
        self.control.write_text(json.dumps({"mode": "normal", "installed": False}))
        self.calls = self.root / "calls.txt"
        self.command = self.root / "fake-cmd"
        program = '''import json,sys,shutil
from pathlib import Path
control=Path(CONTROL);calls=Path(CALLS);installed=Path(INSTALLED)
d=json.loads(control.read_text());args=sys.argv[1:]
with calls.open('a') as f:f.write(' '.join(args)+'\\n')
mode=d['mode'];package='com.google.android.youtube.tv'
if args[:3]==['package','list','packages']:
 if mode=='query-failed':raise SystemExit(1)
 if d['installed'] or mode=='existing':print('package:'+package+' versionCode:'+('99' if mode=='existing' else ('43' if mode=='wrong-version' else '42')))
elif args[:2]==['package','install']:
 if mode=='install-failed':print('Failure [test]');raise SystemExit(1)
 shutil.copyfile(args[-1],installed)
 if mode=='changed-installed':installed.write_bytes(b'changed')
 d['installed']=True;control.write_text(json.dumps(d));print('Success')
elif args[:2]==['package','path']:
 print('package:'+str(installed))
 if mode=='split-installed':print('package:'+str(installed.parent/'split.apk'))
else:raise SystemExit(2)
'''.replace("CONTROL", repr(str(self.control))).replace("CALLS", repr(str(self.calls))).replace("INSTALLED", repr(str(self.installed)))
        self.command.write_text("#!" + sys.executable + "\n" + program)
        self.command.chmod(0o755)
        script = SOURCE.read_text().replace("SOURCE_DIR='/product/etc/firefly/preinstall'", "SOURCE_DIR='" + str(self.payload) + "'")
        script = script.replace("STATE_DIR='/data/misc/firefly-youtube-preinstall'", "STATE_DIR='" + str(self.state) + "'")
        script = script.replace("LOCK_DIR='/dev/firefly-youtube-preinstall-lock'", "LOCK_DIR='" + str(self.root / "lock") + "'")
        script = script.replace("PKG_CMD='/system/bin/cmd'", "PKG_CMD='" + str(self.command) + "'")
        script = script.replace("/data/app/*/base.apk", str(self.root) + "/data/app/*/base.apk")
        # Avoid host-wide sync in this sandbox; production code retains it.
        script = script.replace("\nsync\n", "\n:\n").replace("    sync\n", "    :\n")
        script = script.replace("    sleep 5\n", "    sleep 0\n")
        self.script = self.root / "install.sh"
        self.script.write_text(script)

    def mode(self, name):
        data = json.loads(self.control.read_text())
        data["mode"] = name
        self.control.write_text(json.dumps(data))

    def run_script(self):
        return subprocess.run(["bash", str(self.script)], capture_output=True, text=True, timeout=10)

    def status(self):
        return (self.state / "status").read_text().strip()

    def installs(self):
        return 0 if not self.calls.exists() else sum(line.startswith("package install ") for line in self.calls.read_text().splitlines())

    def test_install_once_and_respect_later_uninstall(self):
        self.assertEqual(self.run_script().returncode, 0)
        self.assertTrue((self.state / "success").exists())
        self.assertEqual(self.installs(), 1)
        self.installed.unlink()
        self.control.write_text(json.dumps({"mode": "normal", "installed": False}))
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.installs(), 1)
        self.assertFalse(self.installed.exists())

    def test_existing_newer_or_unknown_signer_not_overwritten(self):
        self.mode("existing")
        self.assertEqual(self.run_script().returncode, 0)
        self.assertIn("skipped-existing", self.status())
        self.assertEqual(self.installs(), 0)

    def test_bad_source_digest_stops_without_retry(self):
        self.apk.write_bytes(b"modified")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.status(), "source-hash-mismatch")
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.installs(), 0)

    def test_wrong_signer_manifest(self):
        self.config.write_text(self.config.read_text().replace(SIGNER, "a" * 64))
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.status(), "wrong-signer-config")
        self.assertEqual(self.installs(), 0)

    def test_package_query_failure_does_not_install(self):
        self.mode("query-failed")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.status(), "package-manager-not-ready-no-install-attempt")
        self.assertEqual(self.installs(), 0)
        self.assertFalse((self.state / "attempted").exists())
        self.mode("normal")
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.installs(), 1)

    def test_install_failure_is_terminal(self):
        self.mode("install-failed")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.status(), "package-install-failed")
        self.run_script()
        self.assertEqual(self.installs(), 1)
        self.assertFalse((self.state / "success").exists())

    def test_installed_version_check(self):
        self.mode("wrong-version")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.status(), "installed-package-version-mismatch")
        self.assertFalse((self.state / "success").exists())

    def test_installed_exact_signed_bytes_check(self):
        self.mode("changed-installed")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.status(), "installed-hash-mismatch")
        self.assertFalse((self.state / "success").exists())

    def test_unexpected_split_rejected(self):
        self.mode("split-installed")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.status(), "unexpected-installed-splits")
        self.assertFalse((self.state / "success").exists())


if __name__ == "__main__":
    unittest.main()
