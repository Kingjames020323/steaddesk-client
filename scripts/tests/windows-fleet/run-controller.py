#!/usr/bin/env python3
"""Compile the actual patched portable controller with explicit mock Host tests.
No Windows calls, product services, installation, credentials or trust-store edits.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import json
import shutil
import tomllib

p=argparse.ArgumentParser()
p.add_argument('--repo-root',type=Path,required=True)
p.add_argument('--source-root',type=Path,required=True)
p.add_argument('--common-root',type=Path)
p.add_argument('--target-dir',type=Path)
p.add_argument('--lock-file',type=Path)
a=p.parse_args()
repo=a.repo_root.resolve();source=a.source_root.resolve()
core=source/'src/steaddesk_fleet_windows.rs'
common=(a.common_root or source/'libs/hbb_common').resolve()
if not core.is_file() or not (common/'Cargo.toml').is_file():p.error('provide patched source and initialized hbb_common')
with tempfile.TemporaryDirectory(prefix='steaddesk-windows-controller-') as tmp:
 lab=Path(tmp);(lab/'src').mkdir()
 # The real hbb_common supplies signing/verification primitives and identity APIs.
 manifest='''[package]
name="steaddesk-windows-controller-test"
version="0.1.0"
edition="2021"
[dependencies]
hbb_common={path=COMMON}
serde={version="1",features=["derive"]}
serde_json="=1.0.118"
chrono="=0.4.41"
chrono-tz="=0.10.4"
'''.replace('COMMON',json.dumps(common.as_posix()))
 root_manifest=tomllib.loads((source/'Cargo.toml').read_text())
 patches={k:v for k,v in root_manifest.get('patch',{}).get('crates-io',{}).items() if 'git' in v}
 if patches:
  manifest+='\n[patch.crates-io]\n'
  for name,values in patches.items():
   manifest+=name+'={'+','.join(k+'='+json.dumps(v) for k,v in values.items())+'}\n'
 (lab/'Cargo.toml').write_text(manifest)
 lock=a.lock_file or source/'Cargo.lock'
 if lock.is_file():shutil.copy2(lock,lab/'Cargo.lock')
 tests=repo/'scripts/tests/windows-fleet/controller-tests.rs'
 (lab/'src/lib.rs').write_text('#[path='+json.dumps(core.as_posix())+']\npub mod candidate;\n#[cfg(test)]\n#[path='+json.dumps(tests.as_posix())+']\nmod tests;\n')
 env=dict(os.environ)
 flags=' --cfg steaddesk_fleet_portable_test'
 version=subprocess.check_output(['rustc','--version'],text=True).split()[1].split('.')
 if tuple(map(int,version[:2])) >= (1,80):flags+=' --check-cfg=cfg(steaddesk_fleet_portable_test)'
 env['RUSTFLAGS']=(env.get('RUSTFLAGS','')+flags).strip()
 env['CARGO_TARGET_DIR']=str((a.target_dir or lab/'target').resolve())
 run=subprocess.run(['cargo','test','--manifest-path',str(lab/'Cargo.toml'),'--lib','--','--nocapture'],env=env)
 raise SystemExit(run.returncode)
