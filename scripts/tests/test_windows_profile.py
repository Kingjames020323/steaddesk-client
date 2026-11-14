"""Regression cases for the UIA names and values in the locked profile."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from windows_profile import PresetLabels


class WindowsProfileTest(unittest.TestCase):
    expected = (
        "SteadDesk · 🔒", "ID server: relay.example.invalid",
        "Relay server: relay.example.invalid", "API server: https://api.example.invalid",
        "Key: fixture-public-key", "Direct IP access: Off", "LAN discovery: Off",
        "TCP tunneling: Off", "Remote configuration modification: Off",
    )

    def setUp(self):
        self.labels = PresetLabels(self.expected)

    def matched(self, values):
        return set().union(*(self.labels.match(v) for v in values))

    def test_merged_static_name_and_separate_selectable_values(self):
        name = "\n".join([self.expected[0] + "\ufe0f", *(["Configured by SteadDesk"] * 4)])
        values = [name, *self.expected[1:5], "\r\n".join(self.expected[5:])]
        self.assertEqual(self.matched(values), set(self.expected))

    def test_every_exact_field_is_required(self):
        for field in self.expected:
            with self.subTest(field=field):
                others = [v for v in self.expected if v != field]
                for invalid in ("", field + "x", "x" + field):
                    self.assertEqual(self.matched([*others, invalid]), set(others))

    def test_modified_values_and_unrelated_text_are_not_accepted(self):
        for field in self.expected[5:]:
            self.assertFalse(self.labels.match(field.replace("Off", "On")))
        for field in self.expected[1:5]:
            self.assertFalse(self.labels.match(field + ".other"))
        self.assertFalse(self.labels.match("Configured by SteadDesk"))
        self.assertFalse(self.labels.match("Private note: " + self.expected[0]))


if __name__ == "__main__":
    unittest.main()
