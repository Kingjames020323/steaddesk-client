#!/usr/bin/env python3
"""Verify the portable packer's binding without building an installer."""
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch


def main(packer):
    spec = importlib.util.spec_from_file_location("fleet_packer_probe", packer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "SteadDesk.exe"
        original = b"synthetic merchant service contents"
        path.write_bytes(original)
        table = module.generate_md5_table(temp, 1)
        path.write_bytes(b"input changed after compression")
        digest = module.fleet_payload_digest(table, "./SteadDesk.exe")
        assert digest == hashlib.sha256(original).hexdigest()
        entry = next(iter(table.values()))
        ambiguous = {**table, "./STEADDESK.EXE": entry}
        for source, exe in [(table, "./support.exe"), ({}, "./SteadDesk.exe"), (ambiguous, "./SteadDesk.exe")]:
            try:
                module.fleet_payload_digest(source, exe)
            except ValueError:
                continue
            raise AssertionError("Unexpected service selection")
        for selected in (digest, None):
            with patch.dict(os.environ, STEADDESK_PACKED_PAYLOAD_SHA256="external"):
                with patch.object(subprocess, "run") as cargo:
                    module.build_portable(temp, "", selected)
                    assert cargo.call_args.kwargs["env"].get("STEADDESK_PACKED_PAYLOAD_SHA256") == selected
    print("PASS: exact packed service digest; missing, ambiguous and wrong product rejected; inherited override cleared")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
