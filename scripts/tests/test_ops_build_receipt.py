import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "ops-build-receipt.py"


class OpsBuildReceipt(unittest.TestCase):
    def test_selected_flags_are_bound_to_the_actual_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            flags = root / "flags.dart"
            dist = root / "dist"
            dist.mkdir()
            package = dist / "fixture.exe"
            package.write_bytes(b"sample artifact for digest test")
            names = (
                "merchantEdition", "helpEnabled", "opsHealthEnabled", "opsGroupsEnabled",
                "normalCasesEnabled", "fleetAdminEnabled",
            )
            selected = (False, True, True, True, True, False)
            flags.write_text("".join(
                f"const {name} = {str(value).lower()};\n" for name, value in zip(names, selected)
            ))
            args = [sys.executable, str(SCRIPT), str(flags), "support", str(dist)]
            env = dict(os.environ, GITHUB_SHA="123", GITHUB_RUN_ID="456", STEADDESK_FLEET_ADMIN="false")
            subprocess.run(args, check=True, env=env)
            receipt = json.loads((dist / "ops-test-profile.json").read_text())
            self.assertEqual(receipt["sha256"], hashlib.sha256(package.read_bytes()).hexdigest())
            self.assertEqual(receipt["features"], dict(zip(names, selected)))
            flags.write_text(flags.read_text().replace("opsHealthEnabled = true", "opsHealthEnabled = false"))
            mismatch = subprocess.run(args, capture_output=True, text=True, env=env)
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("opsHealthEnabled", mismatch.stderr)
