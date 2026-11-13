"""Read the single APK signing certificate from verified Build Tools 35/37 output."""
import re
import sys


def signer_digest(report):
    counts = re.findall(r"^Number of signers: (\d+)$", report, re.MULTILINE)
    if counts != ["1"]:
        raise ValueError(f"expected exactly one signer, reported counts: {counts!r}")
    pattern = r"^(?:Signer #1|V3\.0 Signer:) certificate SHA-256 digest: ([0-9a-fA-F]{64})$"
    digests = re.findall(pattern, report, re.MULTILINE)
    if len(digests) != 1:
        labels = [line.partition(" digest:")[0] for line in report.splitlines() if "SHA-256 digest:" in line]
        raise ValueError(f"expected one signer certificate SHA-256, matched {len(digests)}, labels: {labels!r}")
    return digests[0].lower()


if __name__ == "__main__":
    try:
        print(signer_digest(sys.stdin.read()))
    except ValueError as exc:
        sys.exit(str(exc))
