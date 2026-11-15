#!/usr/bin/env python3
"""Portable path/ABI tests plus optional real Windows cross-compile/link checks.

Does not execute a Windows installer, alter a trust store, or touch service state.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def run(args):
    subprocess.run([str(x) for x in args],check=True)

with tempfile.TemporaryDirectory(prefix="steaddesk-windows-fleet-") as scratch:
    out=Path(scratch)
    compiler=shutil.which("clang++") or shutil.which("c++")
    if not compiler:raise SystemExit("A C++17 host compiler is required")
    run([compiler,"-std=c++17","-Wall","-Wextra","-Werror",ROOT/"tests/path_policy_test.cpp","-o",out/"path-tests"])
    run([out/"path-tests"])
    mingw=shutil.which("x86_64-w64-mingw32-g++")
    nm=shutil.which("x86_64-w64-mingw32-nm")
    if not mingw or not nm:
        print("Windows cross-compile/link: NOT RUN (MinGW unavailable)")
    else:
        main=out/"main.cpp"
        main.write_text('#include "fleet_installer.h"\nint main(){SdFleetExpected e{};return sd_fleet_prepare(&e,nullptr)==SD_FLEET_ARGUMENT?0:1;}\n')
        flags=["-std=c++17","-DUNICODE","-D_UNICODE","-DNOMINMAX","-D_WIN32_WINNT=0x0602","-Wall","-Wextra","-Werror","-I",ROOT]
        libs=["-l"+x for x in ("wintrust","crypt32","bcrypt","advapi32","version","shell32","ole32","uuid")]
        for edition,test in [("production",False),("test",True)]:
            extra=["-DSD_FLEET_TEST_BUILD"] if test else []
            obj=out/(edition+".o")
            run([mingw,*flags,*extra,"-c",ROOT/"fleet_installer.cpp","-o",obj])
            run([mingw,*flags,*extra,obj,main,*libs,"-o",out/(edition+".exe")])
            symbols=subprocess.check_output([nm,"-g",str(obj)],text=True)
            if ("sd_fleet_test_prepare" in symbols)!=test:raise SystemExit("Test-only admission bypass symbol gate failed")
            for symbol in ("sd_fleet_prepare","sd_fleet_launch","sd_fleet_readback","sd_fleet_payload_digest","sd_fleet_boot_id"):
                if symbol not in symbols:raise SystemExit("Missing C ABI symbol: "+symbol)
        print("Windows production/test cross-compile, link, and symbol gates: PASS")
