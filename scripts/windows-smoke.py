"""Exercise the packaged executable on a network-isolated Windows runner desktop."""

import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageStat
from pywinauto import Desktop
from pywinauto.mouse import click


def label(control):
    try:
        return (control.window_text() + " " + (control.element_info.element.CurrentHelpText or "")).strip()
    except Exception:
        return ""


def wait_for(description, probe, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = probe()
        if result is not None:
            return result
        time.sleep(1)
    raise RuntimeError("Timed out waiting for " + description)


def named(window, text):
    for control in window.descendants():
        value = label(control)
        box = control.rectangle()
        if (text.casefold() in value.casefold() and box.width() > 0 and box.height() > 0
                and control.is_visible()):
            return control
    return None


def press(window, text):
    control = wait_for(text, lambda: named(window, text))
    center = control.rectangle().mid_point()
    click(coords=(center.x, center.y))


def capture(window, name):
    time.sleep(1)
    image = window.capture_as_image()
    if max(ImageStat.Stat(image).stddev) < 5:
        raise RuntimeError("Desktop capture is blank")
    image.save(output / (name + ".png"))


exe = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=True)
subprocess.Popen([str(exe)])
desktop = Desktop(backend="uia")


def application():
    matches = [w for w in desktop.windows() if w.window_text() == "SteadDesk"]
    return matches[0] if matches else None


window = wait_for("SteadDesk main window", application, 120)
window.set_focus()
try:
    wait_for("Settings control", lambda: named(window, "Settings"))
    capture(window, "main")
    press(window, "Settings")
    press(window, "About")
    wait_for("AGPL attribution", lambda: named(window, "AGPL-3.0"))
    capture(window, "about")
    press(window, "Network")
    press(window, "ID/Relay Server")
    for value in ("relay.steaddesk.com", "https://api.steaddesk.com",
                  "J1e7eHb4p8PaTnIc7Ihk+t7JNQi0xBVBGfI+sRr3CfA="):
        wait_for("fixed service field", lambda: named(window, value))
    capture(window, "network")
    print("PASS: release executable opened, attribution and locked service profile visible.")
except Exception:
    print("Visible controls:", [s[:90] for c in window.descendants() if (s := label(c))][:90])
    capture(window, "diagnostic")
    raise
