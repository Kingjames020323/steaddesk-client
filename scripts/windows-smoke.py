"""Verify the packaged app on the isolated Windows desktop; publish only public UI."""

from ctypes import windll, wintypes
import json
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
from pywinauto.mouse import click, move


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
support = os.environ.get("STEADDESK_EDITION") == "support"
recent_fixture = support and os.environ.get("GITHUB_ACTIONS") == "true"
if recent_fixture:
    # The workflow isolates both services before this process starts. Seed a
    # disposable account's local preference before launching the packaged UI.
    product = "SteadDesk Support"
    config = Path(os.environ["APPDATA"]) / product / "config" / (product + "_local.toml")
    config.parent.mkdir(parents=True, exist_ok=True)
    account = "offline-smoke"
    history = [["direct/765432109", "765 432 109", "deviceId"]]
    directory_fixture = os.environ.get("STEADDESK_OPS_GROUPS", "").lower() not in ("true","1")
    if directory_fixture:
        from windows_directory_fixture import seed
        seed(account, product)
    with config.open("x", encoding="utf-8") as handle:
        handle.write("[options]\n")
        for key, value in {
            "access_token": "offline-ui-fixture",
            "support-appearance": "light",
            "user_info": json.dumps({"name": account}),
            "support-recent-search-v1-" + account: json.dumps(history),
        }.items():
            handle.write(f"{key} = {json.dumps(value)}\n")
subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
desktop = Desktop(backend="uia")
product = "SteadDesk Support" if support else "SteadDesk"


def application():
    return next((w for w in desktop.windows() if w.window_text() == product), None)


window = wait_for("SteadDesk main window", application, 120)
window.set_focus()
version = (Path(__file__).resolve().parents[1] / "RELEASE_VERSION").read_text().strip()
if not support:
    id_label = wait_for("merchant ID label", lambda: by_name(window, "This device ID"))
    help_label = wait_for("merchant help heading", lambda: by_name(window, "Need help?"))
    if any(by_name(window, label) for label in ("Enter remote ID", "Recent sessions", "Address book")):
        raise RuntimeError("Merchant offers an outbound connection")
    footer = wait_for("merchant panel version", lambda: by_name(window, "SteadDesk " + version))
    if footer.rectangle().top < help_label.rectangle().bottom:
        raise RuntimeError("Merchant version is outside the footer")
    save_evidence(window, "merchant-home", [id_label, help_label, footer])
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
wait_for("device list status column on startup", lambda: by_name(window, "Status"))
if os.environ.get("STEADDESK_TODAY") == "true":
    # Navigation labels and page content have different roles. A visible rail
    # button alone does not prove that its page was actually opened.
    def nav_button(*labels):
        return next((c for c in controls(window, labels.__contains__)
                     if c.element_info.control_type == "Button"), None)

    # Invoke the same semantic tap exposed to Windows assistive technology.
    # A nav button's midpoint can lie behind the rail tooltip on the runner.
    today_nav = wait_for("Today navigation button", lambda: nav_button("今天", "Today"))
    today_nav.invoke()
    page = wait_for("Today page content", lambda: by_name(window, "今天概览"))
    frame, rect = window.rectangle(), page.rectangle()
    # Only the Today body of this fresh, network-isolated test account is public.
    # Keep the account, local ID, and the rest of the desktop masked.
    body = (max(0, rect.left - frame.left), max(0, rect.top - frame.top),
            min(frame.width(), rect.right - frame.left), min(frame.height(), rect.bottom - frame.top))
    if body[2] <= body[0] or body[3] <= body[1]:
        raise RuntimeError("Today page has no visible content bounds")
    save_evidence(window, "support-today", [today_nav], [body])
    wait_for("Devices navigation button", lambda: nav_button("Devices")).invoke()
    wait_for("device list status column after Today", lambda: by_name(window, "Status"))

send_keys("^k")
if recent_fixture:
    heading = wait_for("recent search heading", lambda: by_name(window, "Recent searches"))
    kind = wait_for("search result type", lambda: by_name(window, "Device ID"))
    target = wait_for("grouped recent ID", lambda: by_name(
        window, "Direct connect ID seven six five four three two one zero nine"))
    clear = wait_for("clear history action", lambda: by_name(window, "Clear all"))
    remove = wait_for("single history removal action", lambda: by_name(window, "Remove"))
    save_evidence(window, "recent-search", [heading, kind, target, clear, remove])
    click_control(remove)
    wait_for("removed last history item", lambda: by_name(window, "No recent searches"))
    send_keys("{ESC}^k")
send_keys("765432109", pause=0.05)
wait_for("numeric search connect action", lambda: by_name(window, "Connect · seven six five four three two one zero nine"))
send_keys("^a{BACKSPACE}")
main_labels = {"Devices", "Device", "Status", "Model", "Actions", "SUNMI", "Windows"}
save_evidence(window, "main", controls(window, main_labels.__contains__))
print("PASS support directory, numeric search and incoming permission dialog", flush=True)

def fixture_row(online):
    tail = "one" if online else "two"
    grouped = "987 654 32" + ("1" if online else "2")
    candidates = controls(window, lambda v: "nine eight seven six five four three two " + tail in v or grouped in v)
    return candidates[0] if candidates else None


def row_point(online):
    row = wait_for("synthetic device row", lambda: fixture_row(online))
    return row.rectangle().mid_point()


def capture_directory(name, extra=()):
    # The header strip (local device ID) and bottom status are excluded. This
    # block contains only the synthetic directory and, when opened, its card.
    row = wait_for("directory fixture", lambda: fixture_row(True))
    frame = window.rectangle()
    top = wait_for("Device heading", lambda: by_name(window, "Status")).rectangle().top
    bottom = min(frame.height() - 48, max(top - frame.top + 130, row.rectangle().bottom - frame.top + 90))
    region = (8, top - frame.top, frame.width() - 8, bottom)
    save_evidence(window, name, [row, *extra], [region])


if recent_fixture and directory_fixture:
    window.maximize()
    wait_for("synthetic online report", lambda: by_name(window, "Online") if
             len(controls(window, lambda name: name == "Online" or "\nOnline" in name)) > 1 else None)
    frame = window.rectangle()
    move(coords=(frame.left+10, frame.top+10))
    capture_directory("directory-default")
    for online, expected_action, filename in ((True, "Connect", "online"), (False, "Details", "offline")):
        point = row_point(online)
        move(coords=(point.x, point.y))
        action = wait_for("hover " + expected_action, lambda: by_name(window, expected_action))
        capture_directory("directory-hover-" + filename, [action])
    move(coords=(frame.left+10, frame.top+10))
    # Tab to a row; traverse using only keyboard input. The selected row
    # exposes its own action button even when the mouse is parked outside.
    for _ in range(80):
        send_keys("{TAB}")
        if by_name(window, "Connect") or by_name(window, "Details"):
            break
    else:
        raise RuntimeError("No device row acquired keyboard focus")
    if by_name(window, "Details"):
        send_keys("{UP}")
    wait_for("keyboard online action", lambda: by_name(window, "Connect"))
    send_keys("{DOWN}")
    selected = wait_for("keyboard offline action", lambda: by_name(window, "Details"))
    capture_directory("directory-keyboard-selected", [selected])
    # Restore the window, then set a narrow logical width without DPI assumptions.
    window.restore()
    scale = windll.user32.GetDpiForWindow(wintypes.HWND(window.handle)) / 96
    windll.user32.SetWindowPos(window.handle, 0, 0, 0, round(980*scale), round(660*scale), 0x16)
    wait_for("model hidden at narrow width", lambda: True if by_name(window, "Model") is None else None)
    capture_directory("directory-narrow")
    window.maximize()

def open_settings():
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

if recent_fixture and directory_fixture:
    # Home contains only these two seeded rows. Save the body below the local
    # ID header. Verify the empty part of the directory actually changed color.
    def capture_home(name, extra=()):
        frame = window.rectangle()
        identity = wait_for("local device button", local_id_button).rectangle()
        scale = windll.user32.GetDpiForWindow(wintypes.HWND(window.handle)) / 96
        # Remove the whole local-ID header and account/status footer. The
        # remaining navigation, group tree and directory use the offline fixture.
        body = (8, identity.bottom - frame.top + 2, frame.width() - 8,
                frame.height() - round(110 * scale))
        if body[1] >= body[3]:
            raise RuntimeError("Cannot isolate the public directory")
        row = wait_for("synthetic online row", lambda: fixture_row(True))
        save_evidence(window, name, [row, *extra], [body])

    def background():
        status = wait_for("status column", lambda: by_name(window, "Status")).rectangle()
        frame = window.rectangle()
        pixel = window.capture_as_image().convert("RGB").getpixel((
            status.mid_point().x - frame.left, frame.height() - 85))
        return max(pixel)
    wait_for("day background", lambda: True if background() >= 200 else None)
    capture_home("appearance-day-home")
    open_settings()
    press(window, "General")
    def closed_appearance(value):
        # Windows UIA merges the card title and the selected label into a
        # single Button. Match the entire name and the actual control role.
        expected = ["Appearance", "Appearance: " + value]
        for control in controls(window, lambda name: name.splitlines() == expected):
            if control.element_info.control_type == "Button" and control.is_enabled():
                return control
        return None

    day_picker = wait_for("closed Appearance: Day picker", lambda: closed_appearance("Day"))
    # The merged rectangle includes the card heading; activate the Flutter
    # semantics action on the button itself instead of clicking the card center.
    day_picker.iface_invoke.Invoke()
    options = {
        label: wait_for("appearance option " + label, lambda label=label: by_name(window, label))
        for label in ("Follow System", "Day", "Night")
    }
    boxes = [el.rectangle() for el in options.values()]
    frame = window.rectangle()
    dropdown = (min(r.left for r in boxes) - frame.left, min(r.top for r in boxes) - frame.top,
                max(r.right for r in boxes) - frame.left, max(r.bottom for r in boxes) - frame.top)
    save_evidence(window, "appearance-settings", list(options.values()), [dropdown])
    click_control(options["Night"])
    wait_for("closed Appearance: Night picker",
             lambda: closed_appearance("Night"))
    press(window, "Home")
    wait_for("dark directory body", lambda: True if background() <= 60 else None)
    capture_home("appearance-night-home")
    point = row_point(False)
    move(coords=(point.x, point.y))
    details = wait_for("hover details action", lambda: by_name(window, "Details"))
    capture_home("appearance-night-hover", [details])
    details.iface_invoke.Invoke()
    # The native button name includes the seeded offline device's spoken ID.
    copy = wait_for("card copy ID", lambda: by_name(
        window, "nine eight seven six five four three two two. Copy ID"))
    safe = controls(window, lambda s: s in {"Overview", "Device ID", "Connect", "Transfer file", "Device status"})
    frame = window.rectangle()
    card_start = min(el.rectangle().left for el in safe + [copy] if el.rectangle().left > frame.mid_point().x)
    card_top = wait_for("fixture card ID", lambda: by_name(window, "Device ID")).rectangle().top
    # Stop above any editable notes/history, retain the synthetic ID and actions.
    card_bottom = wait_for("card status action", lambda: by_name(window, "Device status")).rectangle().bottom
    card_rect = (max(0, card_start-frame.left-10), max(0, card_top-frame.top-6),
                 frame.width()-6, min(frame.height(),card_bottom-frame.top+8))
    save_evidence(window, "appearance-night-card", safe + [copy], [card_rect])
    send_keys("{ESC}")
open_settings()
press(window, "About")
source_name = "基于 RustDesk（AGPL-3.0） · Source code"
wait_for("public source attribution", lambda: by_name(window, source_name))
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
