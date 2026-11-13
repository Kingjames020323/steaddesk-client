import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s1_signer import signer_digest

DIGEST = "ab" * 32


class SignerTests(unittest.TestCase):
    def check(self, lines, count=1):
        return signer_digest(f"Number of signers: {count}\n" + "\n".join(lines))

    def test_build_tools_35_and_37(self):
        for prefix in ("Signer #1", "V3.0 Signer:"):
            self.assertEqual(self.check([f"{prefix} certificate SHA-256 digest: {DIGEST}"]), DIGEST)

    def test_rejects_missing_or_ambiguous_signer(self):
        good = f"V3.0 Signer: certificate SHA-256 digest: {DIGEST}"
        for lines, count in (([good], 2), ([good, good.replace(DIGEST, "cd" * 32)], 1),
                             ([good.replace("certificate", "public key")], 1),
                             ([good.replace("V3.0 Signer:", "Source Stamp Signer")], 1)):
            with self.assertRaises(ValueError):
                self.check(lines, count)
