# SPDX-License-Identifier: MIT
"""Synthetic metadata rejection tests, not an authentic YouTube APK verification."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("youtube_import", ROOT / "scripts/import-youtube-tv.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ImportPolicyTest(unittest.TestCase):
    def setUp(self):
        self.trust = {"package": MOD.PACKAGE, "apk_sha256": "a" * 64,
                      "signer_sha256": MOD.GOOGLE_SIGNER, "version_code": 42,
                      "acquisition": "google-play-export",
                      "signer_provenance": "Synthetic independent reference for host test only",
                      "listing_url": "https://play.google.com/store/apps/details?id=" + MOD.PACKAGE}
        self.badging = ("package: name='com.google.android.youtube.tv' versionCode='42' versionName='test'\n"
                        "sdkVersion:'21'\nleanback-launchable-activity: name='tv.Launcher' label='YouTube'\n")
        self.signature = "Signer #1 certificate SHA-256 digest: " + MOD.GOOGLE_SIGNER + "\n"
        self.entries = ["AndroidManifest.xml", "classes.dex", "lib/arm64-v8a/libtest.so"]

    def check(self, **changes):
        options = dict(badging=self.badging, xmltree="", signature=self.signature,
                       entries=self.entries, trust=self.trust, android_api=37)
        options.update(changes)
        return MOD.validate_metadata(**options)

    def test_trust_record(self):
        MOD.validate_trust(self.trust)
        for key, value in [("package", "com.google.android.youtube"), ("apk_sha256", "bad"),
                           ("signer_sha256", "bad"), ("version_code", 0),
                           ("acquisition", "mirror"), ("signer_provenance", "same APK"),
                           ("listing_url", "https://example.invalid/package")]:
            with self.subTest(field=key), self.assertRaises(ValueError):
                MOD.validate_trust(dict(self.trust, **{key: value}))

    def test_arm64_complete(self):
        self.assertEqual(self.check()["abis"], ["arm64-v8a"])

    def test_current_aapt_min_sdk_label(self):
        self.assertEqual(self.check(badging=self.badging.replace("sdkVersion:", "minSdkVersion:"))["min_sdk"], 21)

    def test_java_only_allowed(self):
        self.assertTrue(self.check(entries=self.entries[:2])["java_only"])

    def test_wrong_package(self):
        with self.assertRaisesRegex(ValueError, "official"):
            self.check(badging=self.badging.replace(MOD.PACKAGE, "com.google.android.youtube"))

    def test_wrong_version(self):
        with self.assertRaisesRegex(ValueError, "Version"):
            self.check(badging=self.badging.replace("versionCode='42'", "versionCode='43'"))

    def test_wrong_certificate(self):
        with self.assertRaisesRegex(ValueError, "signer"):
            self.check(signature=self.signature.replace(MOD.GOOGLE_SIGNER, "c" * 64))

    def test_multiple_signers(self):
        with self.assertRaisesRegex(ValueError, "signer"):
            self.check(signature=self.signature + self.signature.replace("#1", "#2"))

    def test_arm32_only(self):
        self.assertEqual(self.check(entries=[p.replace("arm64-v8a", "armeabi-v7a")
                                            for p in self.entries])["abis"], ["armeabi-v7a"])

    def test_wrong_abi(self):
        with self.assertRaisesRegex(ValueError, "ABI"):
            self.check(entries=[p.replace("arm64-v8a", "x86") for p in self.entries])

    def test_split_rejected(self):
        with self.assertRaisesRegex(ValueError, "Split"):
            self.check(badging=self.badging.replace("versionName='test'", "versionName='test' split='config.arm64'"))
        for xml in ["E: uses-split", "A: android:isSplitRequired(0x0101)=(type 0x12)0xffffffff"]:
            with self.subTest(xml=xml), self.assertRaisesRegex(ValueError, "requires splits"):
                self.check(xmltree=xml)

    def test_high_minimum(self):
        with self.assertRaisesRegex(ValueError, "minimum SDK"):
            self.check(badging=self.badging.replace("sdkVersion:'21'", "sdkVersion:'99'"))

    def test_missing_leanback(self):
        with self.assertRaisesRegex(ValueError, "LEANBACK"):
            self.check(badging=self.badging.replace("leanback-launchable-activity:", "launchable-activity:"))

    def test_incomplete_apk(self):
        with self.assertRaisesRegex(ValueError, "complete"):
            self.check(entries=["AndroidManifest.xml"])

    def test_module_keeps_signed_bytes(self):
        result = MOD.preload_text()
        self.assertIn("PRODUCT_PACKAGES += FireflyYouTubeTVPayload", result)
        self.assertNotIn("YouTubeTV.apk:", result)
        self.assertIn("userdebug eng", result)
        result += MOD.module_text()
        self.assertIn("prebuilt_etc", result)
        self.assertIn('sub_dir: "firefly/preinstall"', result)
        self.assertIn('filename: "YouTubeTV.apk"', result)
        self.assertIn("product_specific: true", result)
        self.assertNotIn("certificate:", result)
        self.assertNotIn("skip_preprocessed_apk_checks", result)
        self.assertNotIn("android_app_import", result)


if __name__ == "__main__":
    unittest.main()
