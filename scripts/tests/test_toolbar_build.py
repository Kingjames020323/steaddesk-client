"""Build selectors isolate staff UI and merchant log collection."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ToolbarBuildTest(unittest.TestCase):
    def test_role_and_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            for folder in ('libs/hbb_common/src', 'flutter/windows/runner',
                           'flutter/android/app/src/main'):
                (tree / folder).mkdir(parents=True)
            (tree / 'RELEASE_VERSION').write_text('test')
            (tree / 'flutter/android/app/src/main/AndroidManifest.xml').write_text(
                '<manifest>\n    <queries></queries>\n    <application>\n'
                '<action android:name="android.intent.action.BOOT_COMPLETED" />\n'
                '    </application>\n</manifest>')
            for edition in ('merchant', 'support'):
                for flag in ('', 'false', 'true', '1', 'invalid'):
                    with self.subTest(edition=edition, flag=flag):
                        result = subprocess.run(
                            ['bash', ROOT / 'scripts/configure-edition.sh', tree, edition],
                            env={**os.environ, 'STEADDESK_TOOLBAR': flag,
                                 'STEADDESK_TOOLBAR_ACTIONS': '',
                                 'STEADDESK_FLEET_UPDATE': 'false'},
                            capture_output=True, text=True)
                        if flag == 'invalid':
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn('STEADDESK_TOOLBAR', result.stderr)
                            continue
                        self.assertEqual(result.returncode, 0, result.stderr)
                        enabled = flag in ('1', 'true')
                        module = 'host' if enabled and edition == 'support' else 'off'
                        self.assertEqual((tree / 'flutter/lib/steaddesk/toolbar_api.dart').read_text(),
                                         f"export 'toolbar/{module}.dart';\n")
                        flags = (tree / 'flutter/lib/steaddesk/fixed_build.dart').read_text()
                        self.assertIn('fixedSupportEnabled = false', flags)
                        self.assertIn('readToolbarEnabled = ' + str(enabled and edition == 'support').lower(), flags)
                        self.assertEqual((tree / 'src/steaddesk_tb.rs').read_text().strip(),
                                         str(enabled and edition == 'merchant').lower())


class FixedActionsBuildTest(unittest.TestCase):
    def test_signing_and_mutations_are_merchant_only_and_require_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            tree = Path(folder)
            for subdir in ('libs/hbb_common/src', 'flutter/windows/runner', 'flutter/android/app/src/main'):
                (tree / subdir).mkdir(parents=True)
            (tree / 'RELEASE_VERSION').write_text('test')
            (tree / 'flutter/android/app/src/main/AndroidManifest.xml').write_text(
                '<manifest>\n    <queries></queries>\n    <application>\n'
                '<action android:name="android.intent.action.BOOT_COMPLETED" />\n'
                '    </application>\n</manifest>')
            for edition in ('support', 'merchant'):
                for flag in ('', 'false', '1', 'true', 'invalid'):
                    with self.subTest(edition=edition, flag=flag):
                        result = subprocess.run(
                            ['bash', ROOT / 'scripts/configure-edition.sh', tree, edition],
                            env={**os.environ, 'STEADDESK_TOOLBAR': '', 'STEADDESK_TOOLBAR_ACTIONS': flag,
                                 'STEADDESK_FLEET_UPDATE': 'false'}, capture_output=True, text=True)
                        if flag == 'invalid':
                            self.assertNotEqual(result.returncode, 0)
                            continue
                        self.assertEqual(result.returncode, 0, result.stderr)
                        enabled = flag in ('1', 'true')
                        merchant = enabled and edition == 'merchant'
                        support = enabled and edition == 'support'
                        lib = tree / 'flutter/lib/steaddesk'
                        self.assertEqual((tree / 'src/steaddesk_fixed_enabled.rs').read_text().strip(), str(merchant).lower())
                        self.assertIn(f"fixed/{'merchant' if merchant else 'off'}.dart", (lib / 'fixed_merchant_api.dart').read_text())
                        flags = (lib / 'fixed_build.dart').read_text()
                        self.assertIn('fixedSupportEnabled = ' + str(support).lower(), flags)
                        self.assertIn('readToolbarEnabled = false', flags)
                        self.assertIn(f"toolbar/{'host' if support else 'off'}.dart", (lib / 'toolbar_api.dart').read_text())
                        native_flag = tree / 'flutter/android/app/src/main/java/com/carriez/flutter_hbb/FixedActionBuild.java'
                        self.assertIn('ENABLED = ' + str(merchant).lower(), native_flag.read_text())
