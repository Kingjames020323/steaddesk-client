"""Verify the packaged app on the isolated Windows desktop; publish only public UI."""

import re
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageStat
from pywinauto import Desktop
from pywinauto.mouse import click


def wait_for(description, probe, timeout=35):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = probe()
        if result is not None:
            return result
        time.sleep(0.5)
    raise RuntimeError("Timed out waiting for " + description)


def controls(window, predicate):
    matches = []
    for control in window.descendants():
        box = control.rectangle()
        if box.width() <= 0 or box.height() <= 0 or not control.is_visible():
            continue
        value = control.window_text().strip()
        if predicate(value):
            matches.append(control)
    return sorted(matches, key=lambda c: c.rectangle().width() * c.rectangle().height())


def by_name(window, name):
    matches = controls(window, lambda s: s.casefold() == name.casefold())
    return matches[0] if matches else None


def press(window, name):
    control = wait_for(name, lambda: by_name(window, name))
    point = control.rectangle().mid_point()
    click(coords=(point.x, point.y))


def save_evidence(window, name, visible_controls, public_regions=()):
    # Default-deny pixels. Never write the original desktop, nearby fields, or
    # the accessibility tree to disk or stdout, including on error.
    original = window.capture_as_image().convert("RGB")
    frame = window.rectangle()
    visible = Image.new("RGB", original.size, "#e3e6e9")
    # These additional regions are anchored to known public page landmarks.
    # The Home credential pane and About identity rows always stay masked.
    for box in public_regions:
        if (0 <= box[0] < box[2] <= original.width
                and 0 <= box[1] < box[3] <= original.height):
            visible.paste(original.crop(box), box[:2])
    count = 0
    for control in visible_controls:
        rect = control.rectangle()
        if rect.width() > frame.width() * 0.85 or rect.height() > frame.height() * 0.38:
            continue
        box = (max(0, rect.left - frame.left), max(0, rect.top - frame.top),
               min(original.width, rect.right - frame.left), min(original.height, rect.bottom - frame.top))
        if box[0] < box[2] and box[1] < box[3]:
            visible.paste(original.crop(box), box[:2])
            count += 1
    if not count or max(ImageStat.Stat(visible).stddev) < 1:
        raise RuntimeError("No verified public pixels for " + name)
    visible.save(output / (name + ".png"))


exe = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=True)
subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
desktop = Desktop(backend="uia")


def application():
    return next((w for w in desktop.windows() if w.window_text() == "SteadDesk"), None)


window = wait_for("SteadDesk main window", application, 120)
window.set_focus()
entry = wait_for("remote ID placeholder", lambda: by_name(window, "Enter remote ID"))
main_labels = {"Enter remote ID", "Your Desktop", "Control Remote Desktop", "Connect",
               "Powered by RustDesk", "Recent sessions", "SteadDesk", "Install"}
frame = window.rectangle()
entry_box = entry.rectangle()
connect = wait_for("Connect", lambda: by_name(window, "Connect")).rectangle()
public_regions = [(0, 0, frame.width(), 28)]
if entry_box.left - frame.left > frame.width() / 4:
    public_regions.append((entry_box.left - frame.left, 32, frame.width(),
                           connect.bottom - frame.top + 5))
save_evidence(window, "main", controls(window, main_labels.__contains__), public_regions)
print("PASS main window", flush=True)

settings = by_name(window, "Settings")
if settings:
    press(window, "Settings")
else:
    # The 1.5.0 overflow button has only a Flutter tooltip on Windows.
    frame = window.rectangle()
    click(coords=(frame.left + round(frame.width() * 0.228),
                  frame.top + round(frame.height() * 0.24)))

press(window, "About")
source_name = "基于 RustDesk（AGPL-3.0） · Source code"
wait_for("public source attribution", lambda: by_name(window, source_name))
tabs = {"General", "Security", "Network", "Display", "Account", "About", "SteadDesk"}
about_labels = tabs | {source_name, "Privacy Statement"}
privacy = wait_for("privacy link", lambda: by_name(window, "Privacy Statement")).rectangle()
# In the pinned About widget every row below Privacy Statement is public
# attribution or licensing. Fingerprint and ID appear above that link.
public_regions = [(0, 0, frame.width(), 28),
                  (0, privacy.top - frame.top, frame.width(), frame.height())]
save_evidence(window, "about", controls(window, lambda s:
              s in about_labels or re.fullmatch(r"Version: [\w.()+ -]{1,30}", s) is not None), public_regions)
print("PASS public About attribution", flush=True)

press(window, "Network")
press(window, "ID/Relay Server")
expected = [
    "SteadDesk · 🔒",
    "ID server: relay.steaddesk.com",
    "Relay server: relay.steaddesk.com",
    "API server: https://api.steaddesk.com",
    "Key: J1e7eHb4p8PaTnIc7Ihk+t7JNQi0xBVBGfI+sRr3CfA=",
]


def public_fields(control):
    values = [control.window_text()]
    for probe in (lambda: control.iface_value.CurrentValue,
                  lambda: control.iface_text.DocumentRange.GetText(-1),
                  lambda: control.iface_legacy_iaccessible.CurrentValue):
        try:
            values.append(probe() or "")
        except Exception:
            pass
    return values


def profile_fields():
    fields = []
    matched = set()
    for control in controls(window, lambda s: True):
        for value in public_fields(control):
            normalized = " ".join(value.replace("\ufe0f", "").split())
            present = {line for line in expected if line in normalized}
            residue = normalized
            for line in expected:
                residue = residue.replace(line, "")
            if present and not residue.strip():
                fields.append(control)
                matched.update(present)
                break
    return fields if matched == set(expected) else None


fields = wait_for("read-only preset values", profile_fields)
wait_for("Close action", lambda: by_name(window, "Close"))
if by_name(window, "OK") or by_name(window, "Apply") or by_name(window, "Save"):
    raise RuntimeError("An edit confirmation is visible")
for field in fields:
    if field.element_info.control_type == "Edit":
        if not field.iface_value.CurrentIsReadOnly:
            raise RuntimeError("A preset field is editable")
save_evidence(window, "network", fields + controls(window, {"ID/Relay server", "Close"}.__contains__))
print("PASS fixed ID, relay, API and public key in read-only profile", flush=True)
