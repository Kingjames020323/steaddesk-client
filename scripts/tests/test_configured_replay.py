"""Rehearse configured and partial patch queues on a tiny offline Git repository."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from edition_selectors import selectors


def run(*args, cwd, check=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


class ConfiguredReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue = self.root / "patches"
        self.queue.mkdir()
        self.author = self.root / "author"
        self.author.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("commit", "-qm", "empty upstream", "--allow-empty")
        self.file = Path("flutter/lib/steaddesk/fixed_build.dart")
        self.defaults = self.generated(False)
        self.enabled = self.generated(True)
        (self.author / self.file).parent.mkdir(parents=True)
        (self.author / self.file).write_bytes(self.defaults)
        (self.author / "feature").write_text("first\n")
        self.patch("0001")
        self.tree = self.root / "tree"
        self.tree.mkdir()
        run("git", "init", "-q", cwd=self.tree)

    def generated(self, enabled):
        flags = selectors(merchant=False, fixed=enabled, toolbar=enabled,
                          today=False, callback=False, kb=False)
        return flags[self.file.as_posix()].encode()

    def git(self, *args):
        return run("git", *args, cwd=self.author).stdout

    def patch(self, name):
        self.git("add", ".")
        (self.queue / (name + ".patch")).write_text(self.git("diff", "--cached", "--binary"))
        self.git("commit", "-qm", name)

    def replay(self, check=True):
        return run("bash", SCRIPTS / "replay-patch-queue.sh", self.queue, cwd=self.tree, check=check)

    def test_repeat_configured_and_append_suffix(self):
        self.replay()
        marker = self.tree / self.file
        self.assertEqual(marker.read_bytes(), self.defaults)
        marker.write_bytes(self.enabled)
        self.replay()
        (self.author / "feature").write_text("first\nsecond\n")
        self.patch("0002")
        self.replay()
        self.assertEqual((self.tree / "feature").read_text(), "first\nsecond\n")
        self.assertEqual(marker.read_bytes(), self.enabled)
        self.replay()
        marker.write_bytes(self.enabled.replace(b"\n", b"\r\n"))
        self.replay()
        self.assertEqual(marker.read_bytes(), self.enabled.replace(b"\n", b"\r\n"))

    def test_partial_configured_tree_can_already_have_selector_from_pending_patch(self):
        (self.tree / self.file).parent.mkdir(parents=True)
        (self.tree / self.file).write_bytes(self.enabled)
        self.replay()
        self.assertEqual((self.tree / "feature").read_text(), "first\n")
        self.assertEqual((self.tree / self.file).read_bytes(), self.enabled)

    def test_locally_mixed_merchant_and_support_outputs_are_preserved_on_failure(self):
        self.replay()
        marker = self.tree / self.file
        marker.write_bytes(self.enabled)
        merchant_module = marker.with_name("fixed_merchant_api.dart")
        merchant_module.write_text("export 'fixed/merchant.dart';\n")
        self.assertNotEqual(self.replay(check=False).returncode, 0)
        self.assertEqual(marker.read_bytes(), self.enabled)
        self.assertEqual(merchant_module.read_text(), "export 'fixed/merchant.dart';\n")

    def test_damaged_checkout_fails_before_writing_other_files(self):
        self.replay()
        marker = self.tree / self.file
        for damage in ("edited", "missing", "executable", "symlink", "ordinary"):
            with self.subTest(damage=damage):
                marker.unlink()
                marker.write_bytes(self.enabled)
                feature = self.tree / "feature"
                feature.write_text("first\n")
                if damage == "edited":
                    marker.write_bytes(self.enabled + b"// local edit\n")
                elif damage == "missing":
                    marker.unlink()
                elif damage == "executable":
                    marker.chmod(0o755)
                elif damage == "symlink":
                    marker.unlink()
                    marker.symlink_to(feature)
                else:
                    feature.write_text("changed locally\n")
                expected = feature.read_bytes()
                self.assertNotEqual(self.replay(check=False).returncode, 0)
                self.assertEqual(feature.read_bytes(), expected)
                if not os.path.lexists(marker):
                    marker.touch()
