"""Guard M-1's patches at the upstream desktop connection/window boundaries."""
import unittest
from pathlib import Path


PATCH = (Path(__file__).resolve().parents[2] / "patches" /
         "0028-support-connection-metrics.patch")


def patched_lines_by_file(path):
    """Read the destination-side lines in each unified-diff hunk."""
    files = {}
    chunk = None
    for line in path.read_text().splitlines():
        if line.startswith("diff --git "):
            chunk = None
        elif line.startswith("+++ b/flutter/lib/"):
            chunk = files.setdefault(line.removeprefix("+++ b/flutter/lib/"), [])
        elif chunk is not None and line.startswith((" ", "+")):
            chunk.append(line[1:])
    return {name: "\n".join(lines) for name, lines in files.items()}


class MetricWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = patched_lines_by_file(PATCH)

    def test_click_seed_reaches_both_remote_window_entry_points(self):
        self.assertIn("SupportMetrics.begin(peer.id)", self.src["common/widgets/peer_card.dart"])
        self.assertIn("metricSeed ??= SupportMetrics.begin(id)", self.src["common.dart"])
        self.assertIn("clicked: false", self.src["common.dart"])
        self.assertIn("SupportMetrics.fromChild", self.src["desktop/pages/desktop_home_page.dart"])
        tabs = self.src["desktop/pages/remote_tab_page.dart"]
        for kind in ("params", "args"):  # fresh window, existing-window method call
            self.assertRegex(tabs, rf"metricSeed:\s*{kind}\[['\"]metric_seed['\"]\]")
        page = self.src["desktop/pages/remote_page.dart"]
        self.assertEqual(page.count("SupportMetrics.attach("), 1)
        self.assertRegex(page, r"widget\.tabWindowId == null && widget\.display == null")

    def test_tab_move_and_monitor_share_the_existing_measurement(self):
        tabs = self.src["desktop/pages/remote_tab_page.dart"]
        self.assertIn("if (close && ffi.metrics != null)", tabs)
        self.assertIn("detachForTransfer()", tabs)
        self.assertIn("SupportMetrics.resume", self.src["models/model.dart"])
        self.assertIn("transferMetricToMonitor", self.src["models/model.dart"])
        self.assertIn("bind.sessionGetConnSessionId", tabs)
        self.assertIn("ffi.metrics = SupportMetrics.resume", tabs)

    def test_shutdown_drains_remote_engines_before_native_destruction(self):
        manager = self.src["utils/multi_window_manager.dart"]
        shutdown = manager.index("'steaddesk.metrics.shutdown'")
        self.assertLess(shutdown, manager.index("_closeWindows(e)", shutdown))
        self.assertIn("await rustDeskWinManager.drainWindowMetrics()",
                      self.src["desktop/pages/remote_tab_page.dart"])
