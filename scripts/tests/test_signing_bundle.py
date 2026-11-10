"""Credential-free checks for the release bundle and Android signer orchestration."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]
PREFIX = "SteadDesk-1.5.0-sd.1-"
APK = PREFIX + "universal.unsigned.apk"
EXE = PREFIX + "x64.unsigned.exe"
SOURCE = PREFIX + "source.tar.gz"


class SigningTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.release = self.root / "unsigned release"
        self.release.mkdir()
        for name in (APK, EXE, SOURCE):
            (self.release / name).write_bytes(name.encode())
        self.manifest = self.checksums(self.release)
        (self.release / "SHA256SUMS").write_bytes(self.manifest)

    @staticmethod
    def checksums(directory):
        lines = []
        for path in sorted(directory.glob("SteadDesk-*")):
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
        return "".join(lines).encode()

    def invoke_android(self, source, output, mode="ok"):
        # An existing non-key file stands in for the operator's path.
        executable = self.root / "apksigner"
        executable.write_text("""#!/usr/bin/env bash
set -eu
if [[ $1 == sign ]]; then
  [[ $2 == --ks && $4 == --ks-key-alias && $6 == --v2-signing-enabled && $7 == true ]] || exit 1
  [[ $8 == --v3-signing-enabled && $9 == true && ${10} == --v4-signing-enabled ]] || exit 1
  [[ ${11} == false && ${12} == --out && $# == 14 ]] || exit 1
  cat "${14}" > "${13}"
  echo 'verifier fixture' >> "${13}"
elif [[ $1 == verify ]]; then
  [[ $# == 4 && $2 == --verbose && $3 == --print-certs && -s $4 ]] || exit 1
  [[ $TEST_MODE != reject ]] || exit 1
  echo 'Verified using v2 scheme (APK Signature Scheme v2): true'
  if [[ $TEST_MODE != missing-v3 ]]; then
    echo 'Verified using v3 scheme (APK Signature Scheme v3): true'
  fi
else
  exit 1
fi
""")
        executable.chmod(0o700)
        return subprocess.run(
            [str(SCRIPTS / "sign-android.sh"), str(source), str(output),
             str(SCRIPTS / "sign-android.sh"), "fixture-alias"],
            env={**os.environ, "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                 "TEST_MODE": mode},
            capture_output=True, text=True,
        )

    def test_composite_manifest_after_both_steps(self):
        scratch = self.root / "scratch"
        scratch.mkdir()
        helper = [sys.executable, str(SCRIPTS / "signing_bundle.py")]
        subprocess.run(helper + ["prepare", "windows", self.release, scratch], check=True,
                       capture_output=True)
        # Exercise only the Windows bundle exchange on this host.
        win_name = EXE.replace(".unsigned.", ".")
        (scratch / win_name).write_bytes(b"verified executable fixture")
        intermediate = self.root / "windows signed"
        subprocess.run(helper + ["publish", "windows", scratch, intermediate], check=True)
        output = self.root / "both signed"
        run = self.invoke_android(intermediate, output)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual({p.name for p in output.iterdir()}, {
            win_name, APK.replace(".unsigned.", "."), SOURCE, "SHA256SUMS",
        })
        self.assertEqual((output / "SHA256SUMS").read_bytes(), self.checksums(output))
        for name in (SOURCE, win_name):
            self.assertEqual((output / name).read_bytes(), (intermediate / name).read_bytes())
        self.assertEqual((self.release / "SHA256SUMS").read_bytes(), self.manifest)

    def test_bad_input_and_bad_verification_leave_no_output(self):
        output = self.root / "destination"
        for mode in ("reject", "missing-v3", "corrupted-input"):
            with self.subTest(mode=mode):
                if mode == "corrupted-input":
                    (self.release / SOURCE).write_bytes(b"changed")
                run = self.invoke_android(self.release, output, mode)
                self.assertNotEqual(run.returncode, 0)
                self.assertFalse(output.exists())
                self.assertEqual(list(self.root.glob(".steaddesk-sign-*")), [])

    def test_existing_destination_is_preserved(self):
        output = self.root / "destination"
        output.mkdir()
        marker = output / "keep"
        marker.write_text("existing")
        self.assertNotEqual(self.invoke_android(self.release, output).returncode, 0)
        self.assertEqual(marker.read_text(), "existing")


if __name__ == "__main__":
    unittest.main()
