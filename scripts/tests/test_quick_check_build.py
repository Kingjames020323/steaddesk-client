"""Keep quick checks independent of the larger ops integration profile."""
from pathlib import Path
import re
import unittest


WORKFLOW = (Path(__file__).resolve().parents[2] / ".github/workflows/build.yml").read_text()


class QuickCheckBuildTest(unittest.TestCase):
    def test_dispatch_input_is_boolean_and_off_by_default(self):
        inputs = WORKFLOW.split("  workflow_dispatch:", 1)[1].split("\npermissions:", 1)[0]
        block = re.search(r"^      steaddesk_quick_check:\n((?:        .+\n)+)", inputs, re.M)
        self.assertIsNotNone(block)
        self.assertIn("        type: boolean\n", block[1])
        self.assertIn("        default: false\n", block[1])

    def test_env_uses_only_explicit_branch_dispatch_or_repository_opt_in(self):
        lines = [line.strip() for line in WORKFLOW.splitlines()
                 if line.startswith("  STEADDESK_QUICK_CHECK:")]
        self.assertEqual(lines, [
            "STEADDESK_QUICK_CHECK: ${{ github.event_name == 'workflow_dispatch' && "
            "github.ref_type == 'branch' && inputs.steaddesk_quick_check && 'true' || "
            "vars.STEADDESK_QUICK_CHECK == 'true' && 'true' || 'false' }}"
        ])
