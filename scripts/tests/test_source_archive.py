"""Local, public-source archive regression. No network or signing tools required."""
import importlib.util
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "archive-source.py"
spec = importlib.util.spec_from_file_location("source_archive", SCRIPT)
source_archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source_archive)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", repo, *args], stderr=subprocess.STDOUT)


def init(repo):
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "--template=")


def snapshot(repo):
    git(repo, "add", "--all")
    git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgSign=false", "commit", "-qm", "fixture")


class SourceArchiveTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name) / "wrapper"
        self.up = self.root / "upstream"
        self.nested = self.up / "library"
        self.output = Path(scratch.name) / "release.tar.gz"
        for repo in (self.root, self.up, self.nested):
            init(repo)
        (self.nested / "source.c").write_text("original library\n")
        snapshot(self.nested)
        (self.up / ".gitignore").write_text("/version.h\n")
        snapshot(self.up)
        (self.root / "RELEASE_VERSION").write_text("1.5.0-sd.1\n")
        (self.root / "scripts").mkdir()
        (self.root / "scripts/apply-patches.sh").write_text(
            'set -eu\nprintf "patched\\n" > "$1/library/source.c"\n'
            'cp RELEASE_VERSION "$1/version.h"\n'
        )
        snapshot(self.root)

    def test_clean_recursive_inputs_and_repeatability(self):
        (self.nested / "source.c").write_text("dirty working tree\n")
        (self.up / "build-output").write_text("untracked\n")
        (self.root / "local.keystore").write_text("untracked filename canary\n")
        source_archive.archive(self.root, self.output)
        first = self.output.read_bytes()
        source_archive.archive(self.root, self.output)
        self.assertEqual(first, self.output.read_bytes())
        with tarfile.open(self.output) as bundle:
            files = {item.name: bundle.extractfile(item).read() for item in bundle if item.isfile()}
        prefix = "SteadDesk-1.5.0-sd.1-source/"
        self.assertEqual(set(files), {prefix + name for name in (
            "RELEASE_VERSION", "scripts/apply-patches.sh", "upstream/.gitignore",
            "upstream/library/source.c", "upstream/version.h")})
        self.assertEqual(files[prefix + "upstream/library/source.c"], b"patched\n")
        self.assertEqual(files[prefix + "upstream/version.h"], b"1.5.0-sd.1\n")

    def test_rejects_missing_nested_checkout_and_preserves_output(self):
        self.output.write_bytes(b"existing archive")
        self.nested.rename(self.up / "moved")
        with self.assertRaisesRegex(ValueError, "initialize recursive submodule"):
            source_archive.archive(self.root, self.output)
        self.assertEqual(b"existing archive", self.output.read_bytes())

    def test_rejects_tracked_credential_filename(self):
        (self.root / "upload.p12").write_text("filename canary only\n")
        snapshot(self.root)
        with self.assertRaisesRegex(ValueError, "excluded credential filename"):
            source_archive.archive(self.root, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
