"""Match the public fixed-profile labels exposed by Flutter through Windows UIA."""

import re


class PresetLabels:
    def __init__(self, expected):
        self.expected = frozenset(expected)
        # Flutter can merge static Text labels (including the managed-setting annotation)
        # into one accessible name while SelectableText exposes a separate value.
        allowed = [*expected, "Configured by SteadDesk"]
        self.labels = re.compile("|".join(map(re.escape, allowed)))

    def match(self, value):
        text = " ".join((value or "").replace("\ufe0f", "").split())
        parts = self.labels.findall(text)
        if " ".join(parts) != text:
            return set()
        return self.expected.intersection(parts)
