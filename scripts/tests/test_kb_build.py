"""Switching editions or disabling KB must not leave the admin editor in the build."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class KnowledgeCardBuildTest(unittest.TestCase):
    def test_reconfigure_same_tree_for_each_edition_and_opt_out(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            for folder in ('libs/hbb_common/src', 'flutter/windows/runner', 'flutter/android/app/src/main'):
                (tree / folder).mkdir(parents=True)
            (tree / 'RELEASE_VERSION').write_text('test')
            (tree / 'flutter/android/app/src/main/AndroidManifest.xml').write_text(
                '<manifest>\n    <queries></queries>\n    <application>\n'
                '<action android:name="android.intent.action.BOOT_COMPLETED" />\n'
                '    </application>\n</manifest>')
            lib = tree / 'flutter/lib/steaddesk'
            for role, value in [('support', 'true'), ('merchant', '1'), ('merchant', None),
                                ('support', 'false'), ('support', 'typo')]:
                with self.subTest(role=role, value=value):
                    env = {k: v for k, v in os.environ.items() if not k.startswith('STEADDESK_')}
                    if value is not None:
                        env['STEADDESK_KB'] = value
                    run = subprocess.run(['bash', ROOT / 'scripts/configure-edition.sh', tree, role],
                                         env=env, capture_output=True, text=True)
                    if value == 'typo':
                        self.assertNotEqual(run.returncode, 0)
                        self.assertIn('STEADDESK_KB', run.stderr)
                        continue
                    self.assertEqual(run.returncode, 0, run.stderr)
                    active = value in ('1', 'true')
                    flags = (lib / 'kb_build.dart').read_text()
                    for edition in ('merchant', 'support'):
                        selected = str(active and role == edition).lower()
                        self.assertIn(f'const {edition}KbEnabled = {selected};', flags)
                    admin = 'admin_host' if active and role == 'support' else 'admin_off'
                    self.assertEqual((lib / 'kb_admin_api.dart').read_text(), f"export 'kb/{admin}.dart';\n")
                    merchant = 'merchant_help_host' if active and role == 'merchant' else 'merchant_help_off'
                    self.assertIn(merchant, (lib / 'merchant_help_api.dart').read_text())
                    self.assertIn('support_help_off', (lib / 'support_help_header_api.dart').read_text())
                    self.assertNotIn('= true;', (lib / 'callback_build.dart').read_text())
