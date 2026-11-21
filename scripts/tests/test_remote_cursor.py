"""Exercise the shipped merchant cursor state and overlay lifecycle on a host JVM."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("remote-cursor")
PACKAGE = Path("flutter/android/app/src/main/java/com/carriez/flutter_hbb")


class RemoteCursorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.tree = Path(temp.name)
        subprocess.run(["git", "init", "-q"], cwd=cls.tree, check=True)
        paths = [PACKAGE / name for name in ("RemoteCursorOverlay.java", "RemoteCursorState.java")]
        patch = ROOT / "patches/0072-merchant-remote-cursor.patch"
        subprocess.run(["git", "apply", *(f"--include={p}" for p in paths), patch],
                       cwd=cls.tree, check=True)
        sources = [cls.tree / p for p in paths]
        for block in (FIXTURE / "platform.java.in").read_text().split("\npackage ")[1:]:
            package = block.split(";")[0]
            name = re.search(r"public class (\w+)", block)[1]
            dest = cls.tree / package.replace(".", "/") / (name + ".java")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("package " + block)
            sources.append(dest)
        subprocess.run(["javac", "-d", cls.tree, *sources, *FIXTURE.glob("*Scenarios.java")],
                       check=True)

    def scenario(self, name):
        subprocess.run(["java", "-cp", self.tree, f"com.carriez.flutter_hbb.{name}"], check=True)

    def test_oriented_pixels_click_and_idle(self):
        self.scenario("CursorScenarios")

    def test_window_flags_coalescing_end_reconnect_and_unbind(self):
        self.scenario("OverlayScenarios")
