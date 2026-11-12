"""Verify the packaged app on the isolated Windows desktop; publish only public UI."""

from ctypes import windll, wintypes
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from windows_profile import PresetLabels

from PIL import Image, ImageStat
from pywinauto import Desktop
from pywinauto.keyboard import send_keys
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


def public_fields(control):
    values = [control.element_info.name or "", control.window_text() or ""]
    for probe in (lambda: control.iface_value.CurrentValue,
                  lambda: control.iface_text.DocumentRange.GetText(-1),
                  lambda: control.legacy_properties().get('Value')):
        try:
            values.append(probe() or "")
        except Exception:
            pass
    return values


def click_control(control):
    point = control.rectangle().mid_point()
    click(coords=(point.x, point.y))


def press(window, name):
    click_control(wait_for(name, lambda: by_name(window, name)))


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
support = os.environ.get("STEADDESK_EDITION") == "support"
product = "SteadDesk Support" if support else "SteadDesk"


def application():
    return next((w for w in desktop.windows() if w.window_text() == product), None)


window = wait_for("SteadDesk main window", application, 120)
window.set_focus()
if not support:
    id_label = wait_for("merchant ID label", lambda: by_name(window, "This device ID"))
    help_label = wait_for("merchant help heading", lambda: by_name(window, "Need help?"))
    if any(by_name(window, label) for label in ("Enter remote ID", "Recent sessions", "Address book")):
        raise RuntimeError("Merchant offers an outbound connection")
    save_evidence(window, "merchant-home", [id_label, help_label])
    print("PASS merchant incoming-only home", flush=True)
    sys.exit(0)


# The support home puts the permission switch in the Local ID dialog. Flutter
# can merge both lines of the button into one UIA name. Never log/capture it.
def local_id_button():
    matches = controls(window, lambda s: s.startswith("Local ID · "))
    return matches[0] if matches else None


click_control(wait_for("local device button", local_id_button))
wait_for("incoming permission switch", lambda: by_name(window, "Allow incoming connections"))
send_keys("{ESC}")

# Exercise the packaged directory and its explicit action without dialing a peer.
wait_for("support directory", lambda: by_name(window, "Devices"))
send_keys("^k")
send_keys("765432109", pause=0.05)
wait_for("numeric search connect action", lambda: by_name(window, "Connect · 765432109"))
send_keys("^a{BACKSPACE}")
main_labels = {"Devices", "Device", "Status", "Model", "Actions", "SUNMI", "Windows"}
save_evidence(window, "main", controls(window, main_labels.__contains__))
print("PASS support directory, numeric search and incoming permission dialog", flush=True)

settings = by_name(window, "Settings")
if settings:
    click_control(settings)
else:
    # In the pinned Windows tab bar, Settings precedes the three window
    # actions. All four buttons are 27 logical pixels wide.
    frame = window.rectangle()
    scale = windll.user32.GetDpiForWindow(wintypes.HWND(window.handle)) / 96
    click(coords=(frame.right - round(3.5 * 27 * scale),
                  frame.top + round(14 * scale)))

press(window, "About")
source_name = "基于 RustDesk（AGPL-3.0） · Source code"
wait_for("public source attribution", lambda: by_name(window, source_name))
version = (Path(__file__).resolve().parents[1] / "RELEASE_VERSION").read_text().strip()
version_label = "Version: " + version


def about_version():
    for control in controls(window, lambda s: True):
        if any(value.strip() == version_label for value in public_fields(control)):
            return control
    return None


wait_for("distribution About version " + version, about_version)
print("PASS About " + version_label, flush=True)
tabs = {"General", "Security", "Network", "Display", "Account", "About", "SteadDesk"}
about_labels = tabs | {source_name, "Privacy Statement"}
privacy = wait_for("privacy link", lambda: by_name(window, "Privacy Statement")).rectangle()
# In the pinned About widget every row below Privacy Statement is public
# attribution or licensing. Fingerprint and ID appear above that link.
frame = window.rectangle()
public_regions = [(0, 0, frame.width(), 28),
                  (0, privacy.top - frame.top, frame.width(), frame.height())]
save_evidence(window, "about", controls(window, lambda s:
              s in about_labels or re.fullmatch(r"Version: [\w.()+ -]{1,30}", s) is not None), public_regions)
print("PASS public About attribution", flush=True)

# Keep the Network tile and the scrollable dialog content in the CI viewport.
window.maximize()
press(window, "Network")
press(window, "ID/Relay Server")
expected = [
    "SteadDesk · 🔒",
    "ID server: relay.steaddesk.com",
    "Relay server: relay.steaddesk.com",
    "API server: https://api.steaddesk.com",
    "Key: J1e7eHb4p8PaTnIc7Ihk+t7JNQi0xBVBGfI+sRr3CfA=",
    "Direct IP access: Off",
    "LAN discovery: Off",
    "TCP tunneling: Off",
    "Remote configuration modification: Off",
]


def network_dialog():
    # The Network page behind the Flutter overlay also exposes the four server
    # values. Use the nearest ancestor shared by the dialog title and its action.
    for close in controls(window, lambda name: name == "Close"):
        scope = close.parent()
        while scope is not None and scope != window:
            if by_name(scope, "About"):
                break  # Settings tabs belong to the underlying page.
            if by_name(scope, "ID/Relay server"):
                return scope
            scope = scope.parent()
    return None


dialog = wait_for("ID/Relay server dialog with Close action", network_dialog)
labels = PresetLabels(expected)


def profile_fields():
    matched = set()
    evidence = []
    for control in controls(dialog, lambda s: True):
        if control.element_info.control_type == "Edit":
            if not control.iface_value.CurrentIsReadOnly:
                raise RuntimeError("A preset field is editable")
        found = set()
        for value in public_fields(control):
            found.update(labels.match(value))
        matched.update(found)
        # A merged UIA name can describe a whole container. Only reveal
        # pixels from leaf controls with verified public text.
        if found and not control.children():
            evidence.append(control)
    return evidence if matched == set(expected) else None


fields = wait_for("read-only preset values", profile_fields)
wait_for("Close action", lambda: by_name(dialog, "Close"))
if by_name(window, "OK") or by_name(window, "Apply") or by_name(window, "Save"):
    raise RuntimeError("An edit confirmation is visible")
save_evidence(window, "network", fields + controls(dialog, {"ID/Relay server", "Close"}.__contains__))
print("PASS fixed ID, relay, API and public key in read-only profile", flush=True)

press(dialog, "Close")
# Directory search offers connections to numeric IDs. Use the packaged CLI
# to exercise the same session refusal on loopback in this isolated desktop.
subprocess.Popen([str(exe), "--connect", "127.0.0.1"],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
notice = "连接未加密，已拒绝，请联系管理员"


def refusal_dialog():
    for view in desktop.windows():
        # Remote-session windows are separate Flutter windows on Windows.
        if view.process_id() != window.process_id() and "steaddesk" not in view.window_text().lower():
            continue
        public = controls(view, lambda s: True)
        matches = [c for c in public if any(v.strip() == notice for v in public_fields(c))]
        if matches:
            return view, matches
    return None


dialog, message = wait_for("unencrypted connection refusal", refusal_dialog)
if by_name(dialog, "Continue"):
    raise RuntimeError("Insecure connection offers a continuation")
save_evidence(dialog, "refusal", message + controls(dialog, {"Connection Error", "Close", "OK"}.__contains__))
print("PASS direct connection refused before transport; no Continue action", flush=True)
