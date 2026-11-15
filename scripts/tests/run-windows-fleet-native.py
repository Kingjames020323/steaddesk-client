#!/usr/bin/env python3
"""Check exact portable controller + concrete Windows Rust host without building RustDesk.

Provide a complete patched pinned source checkout. The compile-only app peers
represent server identity and session APIs; real Windows checks remain in the C++
platform layer. `--target x86_64-pc-windows-gnu` cross-checks the concrete host.
This command does not link/run product service code, perform installation, change
trust stores or create any persistence outside its temporary build directory.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    source = args.source_root.resolve()
    for folder, expected in ((source, "fada664df7a294d1d1a9ca3e7cd3637069122f17"),
                             (source / "libs/hbb_common", "229b904508364c8997aad0fb5af57effac859f60")):
        found = subprocess.check_output(["git", "-C", str(folder), "rev-parse", "HEAD"], text=True).strip()
        if found != expected:
            parser.error("source checkout does not match the recorded pin")
    for name in ("steaddesk_fleet_windows.rs", "steaddesk_fleet_windows_host.rs", "steaddesk_fleet_windows_config.rs"):
        if not (source / "src" / name).is_file():
            parser.error("apply the candidate queue and configure the explicit test build first")
    metadata = tomllib.loads((source / "Cargo.toml").read_text())
    with tempfile.TemporaryDirectory(prefix="steaddesk-windows-native-") as temporary:
        work = Path(temporary)
        (work / "src").mkdir()
        manifest = '''[package]
name="steaddesk-windows-native-check"
version="0.1.0"
edition="2021"
[dependencies]
hbb_common={path=COMMON}
serde={version="1",features=["derive"]}
serde_json="=1.0.118"
chrono="=0.4.41"
chrono-tz="=0.10.4"
reqwest={version="=0.12.24",features=["blocking","json","native-tls"],default-features=false}
[target.'cfg(windows)'.dependencies]
winapi={version="=0.3.9",features=["winbase"]}
'''.replace("COMMON", json.dumps((source / "libs/hbb_common").as_posix()))
        overrides = metadata.get("patch", {}).get("crates-io", {})
        manifest += "\n[patch.crates-io]\n"
        for name, values in overrides.items():
            if isinstance(values, dict) and "git" in values:
                manifest += name + "={" + ",".join(key + "=" + json.dumps(value) for key, value in values.items()) + "}\n"
        (work / "Cargo.toml").write_text(manifest)
        shutil.copyfile(source / "Cargo.lock", work / "Cargo.lock")
        (work / "src/lib.rs").write_text('''#![allow(unexpected_cfgs)]
#[path=CORE] pub mod candidate;
#[cfg(windows)] pub fn is_server()->bool { false }
#[cfg(windows)] pub mod platform { pub mod windows { pub fn is_installed()->bool { false } } }
#[cfg(windows)] pub mod server { pub static AUTHED_CONNS:std::sync::Mutex<Vec<()>>=std::sync::Mutex::new(Vec::new()); }
'''.replace("CORE", json.dumps((source / "src/steaddesk_fleet_windows.rs").as_posix())))
        command = ["cargo", "check", "--manifest-path", str(work / "Cargo.toml")]
        if args.target:
            command.extend(["--target", args.target])
        if args.offline:
            command.append("--offline")
        subprocess.run(command, check=True, env=os.environ.copy())
        print("PASS exact controller/concrete-host type check; no Windows runtime or installation acceptance inferred")


if __name__ == "__main__":
    main()
