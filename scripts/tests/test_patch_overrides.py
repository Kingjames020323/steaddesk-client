"""Paired patch variants must preserve independent changes and fail on ambiguity."""
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "select-patch-overrides.py"


def section(name, new):
    return f"diff --git a/{name} b/{name}\n--- a/{name}\n+++ b/{name}\n@@ -1 +1 @@\n-old\n+{new}\n"


class PatchOverridesTest(unittest.TestCase):
    def test_requires_both_features_and_changes_only_the_overlapping_file(self):
        with tempfile.TemporaryDirectory() as temp:
            queue = Path(temp)
            compat = queue / "compat"
            compat.mkdir()
            output = queue / "selected"
            output.mkdir()
            target = queue / "0078-history.patch"
            target.write_text("History\n" + section("a", "one") + section("b", "two"))
            variant = compat / "0076-0078-history.override.patch"
            variant.write_text(section("a", "paired"))
            command = [sys.executable, SCRIPT, queue, output]
            subprocess.run(command, check=True)
            self.assertEqual(list(output.iterdir()), [])
            (queue / "0076-session.patch").touch()
            subprocess.run(command, check=True)
            self.assertEqual((output / target.name).read_text(),
                             "History\n" + section("a", "paired") + section("b", "two"))
            for path in (target, variant):
                path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
            subprocess.run(command, check=True)
            self.assertEqual((output / target.name).read_bytes(),
                             ("History\n" + section("a", "paired") + section("b", "two"))
                             .replace("\n", "\r\n").encode())
            second = compat / "0076-0078-duplicate.override.patch"
            second.write_text(variant.read_text())
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            second.unlink()
            variant.write_text(section("unrelated", "paired"))
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
