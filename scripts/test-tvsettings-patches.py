#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the pinned TvSettings installer in isolated Git fixtures, without building or installing."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

BASE = "d726afd01e0189180f2e4c61b6c47c556db372da"
FILES = [
    "Settings/src/com/android/tv/settings/connectivity/ConnectivityListener.java",
    "Settings/src/com/android/tv/settings/device/displaysound/ResolutionSelectionFragment.java",
    "Settings/src/com/android/tv/settings/connectivity/NetworkFragment.java",
]


def run(command, **kwargs):
    return subprocess.run(command, capture_output=True, text=True, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aosp", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    port = Path(__file__).resolve().parents[1]
    upstream = args.aosp.resolve() / "packages/apps/TvSettings"
    spec = importlib.util.spec_from_file_location("install_port", port / "scripts/install-port.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    original = {name: subprocess.run(["git", "show", BASE + ":" + name], cwd=upstream,
                                    capture_output=True, check=True).stdout for name in FILES}
    upstream_before = {name: hashlib.sha256((upstream / name).read_bytes()).hexdigest()
                       for name in FILES}
    with tempfile.TemporaryDirectory(prefix="firefly-tvsettings-test-") as temporary:
        aosp = Path(temporary) / "aosp"
        module = aosp / "packages/apps/TvSettings"
        module.parent.mkdir(parents=True)
        run(["git", "clone", "--shared", "--no-checkout", "--quiet", str(upstream), str(module)])
        run(["git", "checkout", BASE, "--", *FILES], cwd=module)
        run(["git", "update-ref", "--no-deref", "HEAD", BASE], cwd=module)
        installer.apply_tvsettings_patches(aosp, port)
        final = {name: (module / name).read_bytes() for name in FILES}
        assert all(final[name] != original[name] for name in FILES)
        installer.apply_tvsettings_patches(aosp, port)
        assert final == {name: (module / name).read_bytes() for name in FILES}
        for name in FILES:
            unrelated = final[name] + b"\n// unrelated local edit\n"
            (module / name).write_bytes(unrelated)
            try:
                installer.apply_tvsettings_patches(aosp, port)
            except RuntimeError as error:
                assert "unrelated local changes" in str(error)
            else:
                raise AssertionError("Unrelated local edit was not rejected")
            assert (module / name).read_bytes() == unrelated
            (module / name).write_bytes(final[name])
        other = run(["git", "-c", "user.name=Port test", "-c",
                     "user.email=port-test@example.invalid", "commit-tree", BASE + "^{tree}",
                     "-m", "Isolated wrong-HEAD fixture"], cwd=module).stdout.strip()
        run(["git", "update-ref", "--no-deref", "HEAD", other], cwd=module)
        try:
            installer.apply_tvsettings_patches(aosp, port)
        except RuntimeError as error:
            assert "requires " + BASE in str(error)
        else:
            raise AssertionError("Wrong upstream commit was not rejected")
        assert final == {name: (module / name).read_bytes() for name in FILES}
    assert upstream_before == {name: hashlib.sha256((upstream / name).read_bytes()).hexdigest()
                               for name in FILES}
    report = {
        "scope": "Exact pinned patch replay and installer rejection behavior; no hardware operation",
        "base_commit": BASE,
        "passed": True,
        "cases": ["initial application", "idempotent repeat", "local edit in every patched file rejected",
                  "wrong upstream commit rejected", "original checkout unchanged"],
        "files": {name: {"before_sha256": hashlib.sha256(original[name]).hexdigest(),
                          "after_sha256": hashlib.sha256(final[name]).hexdigest()} for name in FILES},
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
