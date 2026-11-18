"""Capture packaged quick notes on the dedicated, disposable Windows runner."""
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from PIL import Image
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


def click_control(control):
    point = control.rectangle().mid_point()
    click(coords=(point.x, point.y))


def press(window, name):
    click_control(wait_for(name, lambda: by_name(window, name)))


def save_evidence(window, name, controls):
    # Export only the synthetic, allowlisted phrase and status controls.
    frame = window.rectangle()
    original = window.capture_as_image().convert("RGB")
    visible = Image.new("RGB", original.size, "#e3e6e9")
    for control in controls:
        rect = control.rectangle()
        box = (rect.left - frame.left, rect.top - frame.top,
               rect.right - frame.left, rect.bottom - frame.top)
        if not (0 <= box[0] < box[2] <= original.width and
                0 <= box[1] < box[3] <= original.height and
                rect.width() <= frame.width() * 0.85 and
                rect.height() <= frame.height() * 0.38):
            raise RuntimeError("Quick note evidence is outside its visible control")
        region = original.crop(box)
        if all(lo == hi for lo, hi in region.getextrema()):
            raise RuntimeError("Quick note control is blank")
        visible.paste(region, box[:2])
    visible.save(output / (name + ".png"))


exe = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=True)
product = "SteadDesk Support"
if os.environ.get("GITHUB_ACTIONS") != "true" or any(
    not ipaddress.ip_address(record[4][0]).is_loopback
    for host in ("api.steaddesk.com", "relay.steaddesk.com")
    for record in socket.getaddrinfo(host, None)
):
    raise RuntimeError("Case fixture requires the isolated Windows runner")
# Read-only offline staff identity. The cached profile confers no admin role.
roaming = Path(os.environ["APPDATA"])
config = roaming / product / "config" / (product + "_local.toml")
support_dir = roaming / "Purslane Tech Pte. Ltd" / product
config.parent.mkdir(parents=True, exist_ok=True)
support_dir.mkdir(parents=True, exist_ok=True)
with config.open("x", encoding="utf-8") as file:
    file.write("""[options]
access_token = "offline-fixture-only"
user_info = '{"name":"fixture-staff"}'
""")
at = "2026-01-01T09:00:00Z"
row = dict(id="11111111-1111-4111-8111-111111111111", agent="fixture-staff",
           device_id="765432109", display_name="Fixture printer", note="", appends=[],
           status="draft", started_at=at, ended_at=at, created_at=at, updated_at=at)
with (support_dir / "support-cases-v1.json").open("x", encoding="utf-8") as file:
    json.dump({"version": 1, "accounts": {"fixture-staff": [row]}}, file)
subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
desktop = Desktop(backend="uia")
window = wait_for("SteadDesk Support", lambda: next((
    w for w in desktop.windows() if w.window_text() == product), None), 120)
window.set_focus()
window.maximize()
press(window, "待补结案 1")
candidate = wait_for("fixture case", lambda: next(iter(controls(
    window, lambda text: text.startswith("Fixture printer"))), None))
click_control(candidate)
fallback = wait_for("offline quick note fallback", lambda: by_name(window, "需要连接 ops"))
phrases = [wait_for("default quick note", lambda label=label: by_name(window, label))
           for label in ("+ 重启打印机", "+ 重新插网线", "+ 换纸卷", "+ 重打订单")]
if by_name(window, "编辑常用备注") or by_name(window, "新增常用备注"):
    raise RuntimeError("Ordinary staff exposed an admin control")
save_evidence(window, "quick-notes-offline-staff", [fallback, *phrases])
press(window, "稍后补")
print("PASS packaged support default quick notes on isolated Windows", flush=True)
