"""Today is a support-only entry and must stay absent in ordinary builds."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class TodayBuildTest(unittest.TestCase):
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
                        env['STEADDESK_TODAY'] = value
                    run = subprocess.run(['bash', ROOT / 'scripts/configure-edition.sh', tree, role],
                                         env=env, capture_output=True, text=True)
                    if value == 'typo':
                        self.assertNotEqual(run.returncode, 0)
                        self.assertIn('STEADDESK_TODAY', run.stderr)
                        continue
                    self.assertEqual(run.returncode, 0, run.stderr)
                    active = value in ('1', 'true')
                    module = 'host' if active and role == 'support' else 'off'
                    self.assertEqual((lib / 'today_api.dart').read_text(), f"export 'today/{module}.dart';\n")
                    self.assertNotIn('= true;', (lib / 'kb_build.dart').read_text())
                    self.assertNotIn('= true;', (lib / 'callback_build.dart').read_text())

    def test_ci_enables_only_manual_preview(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        selected = next(line for line in workflow.splitlines() if line.startswith('  STEADDESK_TODAY:'))
        for guard in ("github.event_name == 'workflow_dispatch'", "github.ref == 'refs/heads/preview/ui-v7'",
                      'inputs.steaddesk_today', "|| 'false'"):
            self.assertIn(guard, selected)
        start = workflow.index('    - name: Test opted-in support features')
        step = workflow[start:workflow.index('    - name:', start + 1)]
        self.assertIn('STEADDESK_TODAY=true', step)
        self.assertIn('lib/steaddesk/today', step)
        self.assertIn('flutter test --no-pub test/steaddesk', step)
        self.assertTrue(step.rstrip().endswith('bash .distribution/scripts/configure-edition.sh "$PWD" support'))
