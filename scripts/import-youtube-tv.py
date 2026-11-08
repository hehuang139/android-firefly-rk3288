#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate a locally obtained, unmodified YouTube TV APK; optionally stage it.

The trust record must come from an independently verified Google distribution.
Matching a user-supplied certificate is not proof of that certificate's origin.
No APK is downloaded, rewritten, signed, installed or sent to a device.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlparse
import zipfile

PACKAGE = "com.google.android.youtube.tv"
# Published by Google for this exact TV package on 2026-11-08.
# Rotation needs a separately reviewed update; do not accept an arbitrary new key.
GOOGLE_SIGNER = "21199d112cece428c82cb0df221da24ff8674c7a982a83a17a970eec43305b4a"
SIGNER_SOURCE = "https://www.youtube.com/.well-known/assetlinks.json"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_trust(record):
    require(record.get("package") == PACKAGE, "Trust record package must be official TV identity")
    for name in ("apk_sha256", "signer_sha256"):
        require(bool(re.fullmatch(r"[0-9a-f]{64}", record.get(name, ""))), "Invalid " + name)
    require(record["signer_sha256"] == GOOGLE_SIGNER,
            "Signer is not the independently pinned Google TV certificate")
    require(isinstance(record.get("version_code"), int) and record["version_code"] > 0,
            "Trust record needs a positive version_code")
    require(record.get("acquisition") in ("google-play-export", "licensed-google-distribution",
                                           "mirror-with-google-assetlinks-verification"),
            "Record the trusted acquisition method; mirror metadata is not a trust anchor")
    require(isinstance(record.get("signer_provenance"), str)
            and len(record["signer_provenance"].strip()) >= 20,
            "Describe independent signer verification, not only this APK's own signature")
    url = urlparse(record.get("listing_url", ""))
    require(url.scheme == "https" and url.hostname == "play.google.com"
            and url.path == "/store/apps/details"
            and parse_qs(url.query).get("id") == [PACKAGE], "Use the official TV Play listing")


def attributes(line):
    return dict(re.findall(r"([A-Za-z][A-Za-z0-9_-]*)='([^']*)'", line))


def validate_metadata(badging, xmltree, signature, entries, trust, android_api,
                      supported_abis=("arm64-v8a", "armeabi-v7a")):
    package_lines = [line for line in badging.splitlines() if line.startswith("package:")]
    require(len(package_lines) == 1, "Exactly one package declaration is required")
    package = attributes(package_lines[0])
    require(package.get("name") == PACKAGE, "This is not the official YouTube Android TV package")
    require(int(package.get("versionCode", "0")) == trust["version_code"], "Version code mismatch")
    require(not package.get("split"), "Split APK input is unsupported; do not use a base APK alone")
    require(not re.search(r"E: uses-split\b|isSplitRequired[^\n]*(?:0xffffffff|true)", xmltree),
            "APK requires splits; provide a verified standalone release instead")
    minimum = re.search(r"^(?:minSdkVersion|sdkVersion):'(\d+)'", badging, re.M)
    require(minimum is not None and int(minimum[1]) <= android_api, "Unsupported minimum SDK")
    require(re.search(r"^leanback-launchable-activity:", badging, re.M) is not None,
            "A real LEANBACK_LAUNCHER entry is required")
    launch = attributes(next(line for line in badging.splitlines()
                             if line.startswith("leanback-launchable-activity:")))
    require(bool(launch.get("name")), "TV launch activity is missing")
    signers = re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$",
                         signature, re.M)
    require(len(signers) == 1 and signers[0].lower() == trust["signer_sha256"],
            "Current signer does not match the independently trusted certificate")
    abis = sorted({name.split("/")[1] for name in entries
                   if re.fullmatch(r"lib/[^/]+/[^/]+\.so", name)})
    require(not abis or set(abis).intersection(supported_abis), "No native ABI supported by this product")
    require("AndroidManifest.xml" in entries and "classes.dex" in entries,
            "Not a complete standalone APK")
    required = re.findall(r"^uses-library:'([^']+)'", badging, re.M)
    optional = re.findall(r"^uses-library-not-required:'([^']+)'", badging, re.M)
    require(all(re.fullmatch(r"[A-Za-z0-9_.-]+", item) for item in required + optional),
            "Unexpected shared-library name")
    target = re.search(r"^targetSdkVersion:'(\d+)'", badging, re.M)
    return {"package": package["name"], "version_code": int(package["versionCode"]),
            "version_name": package.get("versionName"), "min_sdk": int(minimum[1]),
            "target_sdk": None if target is None else int(target[1]),
            "abis": abis, "java_only": not abis, "supported_product_abis": list(supported_abis),
            "leanback_activity": launch["name"],
            "signer_sha256": signers[0].lower(), "required_uses_libraries": required,
            "optional_uses_libraries": optional}


def preload_text():
    return '''# Generated local optional package. Original APK is installed by PackageInstaller.
ifeq ($(filter userdebug eng,$(TARGET_BUILD_VARIANT)),)
$(error Firefly optional first-boot installer currently supports userdebug/eng only)
endif
PRODUCT_PACKAGES += FireflyYouTubeTVPayload
PRODUCT_COPY_FILES += \\
    device/firefly/rk3399/apps/youtube-official/youtube-tv.conf:$(TARGET_COPY_OUT_PRODUCT)/etc/firefly/preinstall/youtube-tv.conf \\
    device/firefly/rk3399/apps/youtube-preinstall/install-youtube-tv.sh:$(TARGET_COPY_OUT_PRODUCT)/etc/firefly/preinstall/install-youtube-tv.sh \\
    device/firefly/rk3399/apps/youtube-preinstall/youtube-preinstall.rc:$(TARGET_COPY_OUT_PRODUCT)/etc/init/firefly-youtube-preinstall.rc
'''


def module_text():
    # Generic product data, not a scanned Android application. Do not run APK
    # preprocessing: PackageInstaller must receive the exact Google-signed file.
    return '''// Generated local-only payload. No re-signing or APK preprocessing.
prebuilt_etc {
    name: "FireflyYouTubeTVPayload",
    src: "YouTubeTV.apk",
    filename: "YouTubeTV.apk",
    sub_dir: "firefly/preinstall",
    product_specific: true,
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--trust-record", type=Path, required=True)
    parser.add_argument("--aosp", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--android-api", type=int, default=37)
    parser.add_argument("--supported-abi", action="append", dest="abis",
                        help="Repeat for product ABIs; default RK3399 zygote64_32 supports ARM64 and ARM32")
    parser.add_argument("--stage-dir", type=Path,
                        help="New, isolated youtube-official directory for a private product stage")
    args = parser.parse_args()
    report = {"passed": False, "installed_on_device": False, "apk_modified": False,
              "google_distribution_provenance_independently_verified_by_script": False,
              "account_playback_certification_and_drm_verified": False}
    try:
        apk = args.apk.resolve()
        trust = json.loads(args.trust_record.read_text(encoding="utf-8-sig"))
        validate_trust(trust)
        require(sha256(apk) == trust["apk_sha256"], "APK digest differs from trusted release")
        root = args.aosp.resolve()
        aapt2 = root / "out/host/linux-x86/bin/aapt2"
        zipalign = root / "out/host/linux-x86/bin/zipalign"
        java = root / "prebuilts/jdk/jdk21/linux-x86/bin/java"
        signer = root / "prebuilts/sdk/tools/linux/lib/apksigner.jar"
        def run(command):
            value = subprocess.run(list(map(str, command)), capture_output=True, text=True)
            require(value.returncode == 0, "Tool verification failed: "
                    + Path(str(command[0])).name + "\n" + value.stdout + value.stderr)
            return value.stdout
        signature = run([java, "-jar", signer, "verify", "--verbose", "--print-certs", apk])
        badging = run([aapt2, "dump", "badging", apk])
        xmltree = run([aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", apk])
        with zipfile.ZipFile(apk) as archive:
            require(archive.testzip() is None, "APK ZIP CRC failure")
            names = archive.namelist()
            require(len(names) == len(set(names)), "Duplicate APK archive entries")
        metadata = validate_metadata(badging, xmltree, signature, names, trust, args.android_api,
                                     args.abis or ("arm64-v8a", "armeabi-v7a"))
        run([zipalign, "-c", "-p", "4", apk])
        with tempfile.TemporaryDirectory(prefix="youtube-prebuilt-check-") as temporary:
            command = [sys.executable, root / "build/soong/scripts/check_prebuilt_presigned_apk.py",
                       "--aapt2", aapt2, "--zipalign", zipalign, "--preprocessed", apk,
                       Path(temporary) / "checked.stamp"]
            preload = subprocess.run(list(map(str, command)), capture_output=True, text=True)
        require(sha256(apk) == trust["apk_sha256"], "APK changed during validation")
        report.update(passed=True, metadata=metadata, apk_sha256=trust["apk_sha256"],
                      signature_matches_supplied_trust_record=True,
                      signature_matches_google_published_tv_certificate=True,
                      google_signer_source=SIGNER_SOURCE,
                      signature_and_content_verified=True,
                      preprocessed_checks_passed=preload.returncode == 0,
                      preprocessed_check_output=preload.stdout + preload.stderr,
                      acquisition=trust["acquisition"], listing_url=trust["listing_url"])
        if args.stage_dir:
            destination = args.stage_dir.resolve()
            require(not destination.exists(), "Staging directory already exists; review it before replacing")
            require(destination.name == "youtube-official", "Stage directory must be named youtube-official")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".youtube-stage-", dir=destination.parent) as temporary:
                staged = Path(temporary) / "youtube-official"
                staged.mkdir()
                shutil.copyfile(apk, staged / "YouTubeTV.apk")
                require(sha256(staged / "YouTubeTV.apk") == trust["apk_sha256"], "Staged APK differs")
                (staged / "preload.mk").write_text(preload_text(), encoding="utf-8")
                (staged / "Android.bp").write_text(module_text(), encoding="utf-8")
                (staged / "youtube-tv.conf").write_text(
                    "sha256=" + trust["apk_sha256"] + "\nversion_code=" + str(trust["version_code"])
                    + "\npackage=" + PACKAGE + "\nsigner_sha256=" + GOOGLE_SIGNER + "\n", encoding="utf-8")
                (staged / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                staged.rename(destination)
            report["staged_directory"] = str(destination)
            report["delivery"] = "Unmodified APK as product data; one bounded boot-complete PackageInstaller attempt"
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        report.update(passed=False, error=str(error))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
