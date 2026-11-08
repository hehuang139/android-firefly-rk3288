# SPDX-License-Identifier: MIT
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/stage-rk3399-legacy-apps.py'
spec = importlib.util.spec_from_file_location('legacy_stager', SCRIPT)
stager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stager)


class UsesLibraryTest(unittest.TestCase):
    def test_bv_preserves_declaration_as_metadata_but_omits_private_build_dep(self):
        declared = ['android.ext.adservices']
        lines, included, omitted = stager.uses_library_build_properties('dev.aaa1115910.bv', [], declared)
        self.assertEqual(declared, ['android.ext.adservices'])
        self.assertEqual(included, [])
        self.assertEqual(omitted, declared)
        self.assertIn('    enforce_uses_libs: false,', lines)
        self.assertFalse(any('optional_uses_libs:' in line for line in lines))

    def test_required_library_cannot_use_optional_exception(self):
        with self.assertRaises(ValueError):
            stager.uses_library_build_properties('dev.aaa1115910.bv', ['android.ext.adservices'], [])

    def test_other_app_optional_library_remains_a_dependency(self):
        lines, included, omitted = stager.uses_library_build_properties('another.app', [], ['android.ext.adservices'])
        self.assertEqual(included, ['android.ext.adservices'])
        self.assertEqual(omitted, [])
        self.assertNotIn('    enforce_uses_libs: false,', lines)

    def test_iqiyi_required_runner_and_other_optional_libraries_stay(self):
        lines, included, omitted = stager.uses_library_build_properties(
            'com.gitvdemo.video', ['android.test.runner'], ['org.apache.http.legacy'])
        self.assertIn('    uses_libs: ["android.test.runner"],', lines)
        self.assertEqual(included, ['org.apache.http.legacy'])
        self.assertEqual(omitted, [])


if __name__ == '__main__':
    unittest.main()
