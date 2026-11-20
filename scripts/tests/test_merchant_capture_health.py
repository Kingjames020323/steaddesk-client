"""Exercise the shipped merchant STATUS/WAKE transactions with host-side service and JNI fakes."""
import platform
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).with_name("capture-health")
PACKAGE = "com.carriez.flutter_hbb"
MERCHANT = Path("flutter/android/app/src/steaddeskMerchant/java/com/carriez/flutter_hbb")


class MerchantCaptureTests(unittest.TestCase):
    def test_status_and_legacy_wake(self):
        with tempfile.TemporaryDirectory() as temp:
            tree = Path(temp)

            def run(*args):
                subprocess.run(args, cwd=tree, check=True)

            run("git", "init", "--quiet")
            sources = [MERCHANT / name for name in ["MerchantRecovery.java", "AgentWakeService.java"]]
            for patch in sorted((ROOT / "patches").glob("*.patch")):
                run("git", "apply", *(f"--include={path}" for path in sources), patch)

            # Split fake platform declarations into Java's required per-public-type files.
            declarations = (FIXTURES / "platform.java.in").read_text().split("\npackage ")[1:]
            for declaration in declarations:
                package_name = declaration.split(";", 1)[0]
                name = re.search(r"public (?:abstract )?(?:class|interface|@interface) (\w+)", declaration)[1]
                path = tree.joinpath(*package_name.split("."), name + ".java")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("package " + declaration)
                sources.append(path)

            # Resolve java.home from the selected java executable on both Linux and macOS.
            properties = subprocess.run(["java", "-XshowSettings:properties", "-version"],
                                        capture_output=True, text=True, check=True).stderr
            include = Path(re.search(r"(?m)^\s*java.home = (.+)$", properties)[1]) / "include"
            macos = platform.system() == "Darwin"
            library = tree / ("librustdesk.dylib" if macos else "librustdesk.so")
            run("cc", "-dynamiclib" if macos else "-shared", "-fPIC", "-I", include,
                "-I", include / ("darwin" if macos else "linux"), FIXTURES / "session.c", "-o", library)
            run("javac", "-d", tree, *sources, FIXTURES / "BinderScenarios.java")
            run("java", f"-Djava.library.path={tree}", "-cp", tree, PACKAGE + ".BinderScenarios")
