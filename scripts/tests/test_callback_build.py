"""Callback enrollment must select the matching help UI and stay off on tags."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CallbackBuildTest(unittest.TestCase):
    def test_edition_selection(self):
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
            for edition in ('support', 'merchant'):
                for flag in ('', 'false', 'true', '1', 'invalid'):
                    with self.subTest(edition=edition, flag=flag):
                        result = subprocess.run(
                            ['bash', ROOT / 'scripts/configure-edition.sh', tree, edition],
                            env={**os.environ, 'STEADDESK_CALLBACK': flag,
                                 'STEADDESK_HELP': 'false', 'STEADDESK_KB': 'false',
                                 'STEADDESK_FLEET_UPDATE': 'false'},
                            capture_output=True, text=True)
                        if flag == 'invalid':
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn('STEADDESK_CALLBACK', result.stderr)
                            continue
                        self.assertEqual(result.returncode, 0, result.stderr)
                        lib = tree / 'flutter/lib/steaddesk'
                        enabled = flag in ('true', '1')
                        constants = (lib / 'callback_build.dart').read_text()
                        for role in ('support', 'merchant'):
                            selected = str(enabled and role == edition).lower()
                            self.assertIn(f'const {role}CallbacksEnabled = {selected};', constants)
                        help_select = (lib / ('merchant_help_api.dart' if edition == 'merchant'
                                              else 'support_help_header_api.dart')).read_text()
                        self.assertIn('_host.dart' if enabled else '_off.dart', help_select)

    def test_manual_preview_only(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        line = next(line for line in workflow.splitlines() if line.startswith('  STEADDESK_CALLBACK:'))
        for guard in ("github.event_name == 'workflow_dispatch'", "github.ref_type == 'branch'",
                      "github.ref == 'refs/heads/preview/ui-v7'", 'inputs.steaddesk_callback',
                      "|| 'false'"):
            self.assertIn(guard, line)
