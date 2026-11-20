#!/usr/bin/env python3
"""Trusted build inputs only: no downloaded keyring or runtime root changes."""
import base64
import json
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit

DEFAULT_PUBLIC = "SF8GBrsbthApL5CJGCzDdDwIA//1Nm0zLBN/wa6UCE0="

def configure(tree, merchant):
    value = os.environ.get("STEADDESK_FLEET_UPDATE", "").strip().lower()
    if value not in ("", "0", "1", "false", "true"):
        raise ValueError("STEADDESK_FLEET_UPDATE must be true, false, 1 or 0")
    enabled = merchant and value in ("true", "1")
    if enabled and (os.environ.get("GITHUB_REF_TYPE") == "tag" or os.environ.get("GITHUB_REF", "").startswith("refs/tags/")):
        raise ValueError("Test release roots cannot be compiled into tagged releases")
    public = os.environ.get("STEADDESK_FLEET_TEST_PUBLIC_KEY", "").strip() or DEFAULT_PUBLIC
    key_id = os.environ.get("STEADDESK_FLEET_TEST_KEY_ID", "").strip() or "test-upd2-v1"
    if not re.fullmatch(r"test-[A-Za-z0-9_.-]{1,58}", key_id):
        raise ValueError("Fleet preview key ID must start with test-")
    decoded = base64.b64decode(public, validate=True)
    if len(decoded) != 32 or base64.b64encode(decoded).decode() != public:
        raise ValueError("Expected a canonical base64 Ed25519 public key")
    def origin(name, default=""):
        value = os.environ.get(name, "").strip() or default
        if not enabled and not value:
            return ""
        parts = urlsplit(value)
        if (not value.isascii() or any(ord(c) < 33 or ord(c) == 127 or c == chr(92) for c in value)
                or parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None
                or parts.path not in ("", "/") or parts.query or parts.fragment):
            raise ValueError(name + " must be an HTTPS origin")
        # Parsing the port also validates its range and spelling.
        if parts.port == 0:
            raise ValueError(name + " cannot use port zero")
        return value.rstrip("/")
    ops = origin("STEADDESK_FLEET_OPS_ORIGIN")
    artifact = origin("STEADDESK_FLEET_ARTIFACT_ORIGIN", ops)
    profile = os.environ.get("STEADDESK_FLEET_SILENT_PROFILE", "").strip()
    if profile and not re.fullmatch(r"[0-9a-f]{64}", profile):
        raise ValueError("Expected SHA-256 of approved firmware fingerprint")
    native = tree / "src"
    native.mkdir(parents=True, exist_ok=True)
    # Only the opt-in Windows merchant module includes these constants at compile time.
    config = native / "steaddesk_fleet_windows_config.rs"
    platform = native / "platform/steaddesk_fleet"
    platform_sources = ("fleet_installer.h", "fleet_installer.cpp")

    if enabled:
        release = (tree / "RELEASE_VERSION").read_text().strip()
        numeric_version = "1.5.0-sd.8" if release == "1.5.0-sd.8-test" else release
        match = re.fullmatch(r"1\.5\.0-sd\.([1-9][0-9]{0,4})", numeric_version)
        if not match or int(match[1]) > 65535:
            raise ValueError("Unsupported Windows release version")
        windows_profile = os.environ.get("STEADDESK_FLEET_WINDOWS_PROFILE", "").strip()
        if windows_profile and not re.fullmatch(r"[0-9a-f]{64}", windows_profile):
            raise ValueError("Expected 64 hexadecimal digits for the Windows install profile")
        strings = {
            "OPS_ORIGIN": ops,
            "ARTIFACT_ORIGIN": artifact,
            "KEY_ID": key_id,
            "PUBLIC_KEY": public,
            "SILENT_PROFILE": windows_profile,
        }
        lines = [f"pub const {name}: &str = {json.dumps(text)};" for name, text in strings.items()]
        lines.extend([
            "pub const KEY_VALID_FROM: u64 = 1767225600;",
            "pub const KEY_VALID_UNTIL: u64 = 1924992000;",
            f"pub const CURRENT_BUILD: u64 = {int(match[1])};",
        ])
        config.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assets = Path(__file__).resolve().parents[1] / "windows-fleet"
        platform.mkdir(parents=True, exist_ok=True)
        for filename in platform_sources:
            shutil.copyfile(assets / filename, platform / filename)
    else:
        config.unlink(missing_ok=True)
        for filename in platform_sources:
            (platform / filename).unlink(missing_ok=True)
    (tree / "src/steaddesk_fleet.rs").write_text(str(enabled).lower()+"\n")
    (tree / "src/steaddesk_fleet_key.rs").write_text(json.dumps(public)+"\n")
    source = tree / "flutter/android/app/src"
    out = source / "steaddeskFleet"
    if out.exists():
        shutil.rmtree(out)
    main = source / "main/java/com/carriez/flutter_hbb"
    main.mkdir(parents=True, exist_ok=True)
    if enabled:
        assets = Path(__file__).resolve().parent.parent / "android-fleet"
        shutil.copytree(assets / "src/main/java", out / "java")
        shutil.copytree(assets / "src/main/res", out / "res")
        package = out / "java/com/carriez/flutter_hbb"
        constants = {"OPS_ORIGIN":ops,"ARTIFACT_ORIGIN":artifact,"KEY_ID":key_id,"PUBLIC_KEY":public,"SILENT_PROFILE":profile}
        body = "package com.carriez.flutter_hbb;\n\nfinal class FleetBuild {\n"
        body += "".join("    static final String "+key+" = "+json.dumps(v)+";\n" for key,v in constants.items())
        body += "    static final long KEY_VALID_FROM = 1767225600L;\n    static final long KEY_VALID_UNTIL = 1924992000L;\n    private FleetBuild() {}\n}\n"
        (package / "FleetBuild.java").write_text(body)
        manifest = source / "steaddeskStaging/AndroidManifest.xml"
        text = manifest.read_text()
        for permission in ("android.permission.REQUEST_INSTALL_PACKAGES", "android.permission.UPDATE_PACKAGES_WITHOUT_USER_ACTION"):
            if permission not in text:
                text = text.replace("    <application", '    <uses-permission android:name="'+permission+'" />\n    <application', 1)
        text = text.replace("    </application>", (assets / "manifest.xml").read_text()+"    </application>")
        manifest.write_text(text)
    call = "FleetUpdater.start(context);" if enabled else ""
    (main / "FleetEntry.java").write_text("package com.carriez.flutter_hbb;\n\npublic final class FleetEntry {\n    public static void start(android.content.Context context) { "+call+" }\n    private FleetEntry() {}\n}\n")

if __name__ == "__main__":
    configure(Path(sys.argv[1]), sys.argv[2] == "merchant")
