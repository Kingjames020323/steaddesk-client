import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "retry-vcpkg-download.sh"
OUTAGE = ("error: curl operation failed with response code 503.\n"
          "CMake Error at scripts/cmake/vcpkg_download_distfile.cmake:134 (message):\n"
          "  Download failed, halting portfile.")


class VcpkgRetry(unittest.TestCase):
    def exercise(self, logs, expected, waits):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for n, content in enumerate(logs):
                (path / str(n)).write_text(content)
            (path / "count").write_text("0")
            (path / "sleep").write_text('#!/bin/bash\necho "$1" >> waits\n')
            (path / "sleep").chmod(0o755)
            cmd = 'n=$(cat count); echo $((n+1)) > count; cat "$n"; test ! -s "$n" || exit 23'
            proc = subprocess.run(["bash", SCRIPT, "bash", "-c", cmd], cwd=path,
                                  env={**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"]},
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, expected, proc.stderr)
            self.assertEqual(int((path / "count").read_text()), len(logs))
            actual = (path / "waits").read_text().splitlines() if (path / "waits").exists() else []
            self.assertEqual(actual, waits)

    def test_recovers_and_stops_at_three(self):
        self.exercise([OUTAGE, ""], 0, ["30"])
        self.exercise([OUTAGE] * 3, 23, ["30", "60"])

    def test_success_and_other_failures(self):
        self.exercise([""], 0, [])
        for msg in (OUTAGE.replace("503", "404"), OUTAGE + "\nerror: SHA512 hash mismatch",
                    OUTAGE.replace("vcpkg_download_distfile", "vcpkg_cmake_build"), "compiler exited 1"):
            with self.subTest(msg=msg):
                self.exercise([msg], 23, [])
