#!/usr/bin/env python3
"""Check the selected Dart build constants and bind the receipt to its package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re


def write_receipt(constants, edition, dist):
    source = constants.read_text(encoding="utf-8")
    support = edition == "support"
    expected = {
        "merchantEdition": not support,
        "helpEnabled": True,
        "opsHealthEnabled": support,
        "opsGroupsEnabled": support,
        "normalCasesEnabled": support,
        "fleetAdminEnabled": support and os.environ.get("STEADDESK_FLEET_ADMIN") == "true",
    }
    for name, selected in expected.items():
        actual = re.findall(rf"^const {name} = (true|false);$", source, re.MULTILINE)
        if actual != [str(selected).lower()]:
            raise ValueError(f"Generated feature does not match the selected profile: {name}")
    packages = [p for p in dist.iterdir() if p.suffix.lower() in (".exe", ".apk")]
    if len(packages) != 1:
        raise ValueError("Expected exactly one installer in the artifact")
    package = packages[0]
    digest = hashlib.sha256()
    with package.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    receipt = {
        "features": expected,
        "commit": os.environ["GITHUB_SHA"],
        "run": os.environ["GITHUB_RUN_ID"],
        "package": package.name,
        "sha256": digest.hexdigest(),
    }
    (dist / "ops-test-profile.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("constants", type=Path)
    parser.add_argument("edition", choices=("merchant", "support"))
    parser.add_argument("dist", type=Path)
    options = parser.parse_args()
    write_receipt(options.constants, options.edition, options.dist)
