"""Edition-generated selectors which also have defaults in the patch queue."""
from itertools import product
from pathlib import Path
import stat
import sys


def selectors(*, merchant, today, toolbar, fixed, callback, kb):
    def boolean(value):
        return str(value).lower()

    def export(module):
        return f"export '{module}.dart';\n"

    lib = "flutter/lib/steaddesk/"
    java = "flutter/android/app/src/main/java/com/carriez/flutter_hbb/"
    return {
        lib + "today_api.dart": export("today/host" if today and not merchant else "today/off"),
        lib + "toolbar_api.dart": export("toolbar/host" if (fixed or toolbar) and not merchant else "toolbar/off"),
        lib + "fixed_build.dart": (
            f"const fixedSupportEnabled = {boolean(fixed and not merchant)};\n"
            f"const readToolbarEnabled = {boolean(toolbar and not merchant)};\n"
        ),
        lib + "fixed_merchant_api.dart": export("fixed/merchant" if fixed and merchant else "fixed/off"),
        lib + "callback_build.dart": (
            f"const merchantCallbacksEnabled = {boolean(callback and merchant)};\n"
            f"const supportCallbacksEnabled = {boolean(callback and not merchant)};\n"
        ),
        lib + "kb_build.dart": (
            f"const merchantKbEnabled = {boolean(kb and merchant)};\n"
            f"const supportKbEnabled = {boolean(kb and not merchant)};\n"
        ),
        lib + "kb_admin_api.dart": export("kb/admin_host" if kb and not merchant else "kb/admin_off"),
        "src/steaddesk_tb.rs": boolean(toolbar and merchant) + "\n",
        "src/steaddesk_fixed_enabled.rs": boolean(fixed and merchant) + "\n",
        java + "FixedActionBuild.java": (
            "package com.carriez.flutter_hbb;\nfinal class FixedActionBuild { static final boolean ENABLED = "
            + boolean(fixed and merchant) + "; }\n"
        ),
    }


def configured_paths(root):
    # Accept only complete files that our own renderer can produce. A handwritten
    # addition, wrong type or executable bit must never be discarded on replay.
    names = ("merchant", "today", "toolbar", "fixed", "callback", "kb")
    profiles = [selectors(**dict(zip(names, values))) for values in product((False, True), repeat=6)]
    present = []
    for name in profiles[0]:
        path = root / name
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(mode) or mode & 0o111:
            raise ValueError(f"Unexpected type or mode for generated selector: {name}")
        data = path.read_bytes()
        # Existing Windows configurations can contain CRLF. Keep exact bytes in
        # each comparison so mixed line endings or user-added lines still fail.
        def matches(profile):
            encoded = profile[name].encode("utf-8")
            return data in (encoded, encoded.replace(b"\n", b"\r\n"))

        profiles = [profile for profile in profiles if matches(profile)]
        if not profiles:
            raise ValueError(f"No single edition configuration matches the selector set at {name}")
        present.append(name)
    return present


if __name__ == "__main__":
    for name in configured_paths(Path(sys.argv[1])):
        print(name)
