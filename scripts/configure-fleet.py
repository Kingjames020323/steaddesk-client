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

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate fleet keyring member")
        result[key] = value
    return result


def release_roots():
    from nacl.bindings import crypto_core_ed25519_is_valid_point

    tagged = os.environ.get("GITHUB_REF_TYPE") == "tag" or os.environ.get("GITHUB_REF", "").startswith("refs/tags/")
    encoded = os.environ.get("STEADDESK_FLEET_KEYRING", "")
    legacy_id = os.environ.get("STEADDESK_FLEET_TEST_KEY_ID", "").strip()
    legacy_public = os.environ.get("STEADDESK_FLEET_TEST_PUBLIC_KEY", "").strip()
    if legacy_id and not re.fullmatch(r"test-[A-Za-z0-9_.-]{1,58}", legacy_id):
        raise ValueError("Invalid legacy preview key ID")
    if (encoded or tagged) and (legacy_id or legacy_public):
        raise ValueError("Legacy preview roots cannot be combined with a keyring or tagged build")
    if len(encoded.encode("utf-8")) > 32768:
        raise ValueError("Release keyring exceeds 32768 bytes")
    if encoded:
        roots = json.loads(encoded, object_pairs_hook=unique_object)
    elif tagged:
        raise ValueError("Enabled tagged builds require an explicit release keyring")
    else:
        roots = {legacy_id or "test-upd2-v1": {
            "public_key": legacy_public or DEFAULT_PUBLIC, "revoked": False,
            "valid_from": 1767225600, "valid_until": 1924992000,
        }}
    if not isinstance(roots, dict) or not roots:
        raise ValueError("Expected a nonempty fleet keyring object")
    revoked_keys = set()
    for key_id, record in roots.items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", key_id) or key_id.startswith("test-") == tagged:
            raise ValueError("Release key ID does not match build type")
        if not isinstance(record, dict) or set(record) != {"public_key", "revoked", "valid_from", "valid_until"}:
            raise ValueError("Invalid public release record")
        public = record["public_key"]
        if not isinstance(public, str) or len(public) != 44:
            raise ValueError("Expected a canonical base64 Ed25519 public key")
        raw = base64.b64decode(public, validate=True)
        if len(raw) != 32 or base64.b64encode(raw).decode() != public or not crypto_core_ed25519_is_valid_point(raw):
            raise ValueError("Invalid Ed25519 public key")
        if tagged and public == DEFAULT_PUBLIC:
            raise ValueError("Built-in preview root cannot be used in tagged builds")
        start, end = record["valid_from"], record["valid_until"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end < 2**63:
            raise ValueError("Invalid release key validity")
        if type(record["revoked"]) is not bool:
            raise ValueError("Invalid release key revocation")
        if record["revoked"]:
            revoked_keys.add(public)
    # Revocation applies to the signing key, including its other IDs and windows.
    for record in roots.values():
        if record["public_key"] in revoked_keys:
            record["revoked"] = True
    return roots


def root_arguments(key_id, record, suffix):
    return ", ".join([json.dumps(key_id), json.dumps(record["public_key"]),
                      str(record["valid_from"]) + suffix, str(record["valid_until"]) + suffix,
                      str(record["revoked"]).lower()])


def configure(tree, merchant):
    value = os.environ.get("STEADDESK_FLEET_UPDATE", "").strip().lower()
    if value not in ("", "0", "1", "false", "true"):
        raise ValueError("STEADDESK_FLEET_UPDATE must be true, false, 1 or 0")
    enabled = merchant and value in ("true", "1")
    roots = release_roots() if enabled else {}
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
        match = re.fullmatch(r"1\.5\.0-sd\.([1-9][0-9]{0,4})", release)
        if not match or int(match[1]) > 65535:
            raise ValueError("Unsupported Windows release version")
        windows_profile = os.environ.get("STEADDESK_FLEET_WINDOWS_PROFILE", "").strip()
        if windows_profile and not re.fullmatch(r"[0-9a-f]{64}", windows_profile):
            raise ValueError("Expected 64 hexadecimal digits for the Windows install profile")
        strings = {
            "OPS_ORIGIN": ops,
            "ARTIFACT_ORIGIN": artifact,
            "SILENT_PROFILE": windows_profile,
        }
        lines = [f"pub const {name}: &str = {json.dumps(text)};" for name, text in strings.items()]
        lines.append(f"pub const CURRENT_BUILD: u64 = {int(match[1])};")
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
    root_source = native / "steaddesk_fleet_root.rs"
    pins = native / "steaddesk_fleet_key.rs"
    # cbindgen follows explicit module paths even for cfg-disabled platforms.
    # Give it the same source in every edition. Disabled builds select zero roots.
    shutil.copyfile(Path(__file__).resolve().parents[1] / "fleet-trust/release_root.rs", root_source)
    pins.write_text("&[\n" + "".join(
        f"    ReleaseRoot::new({root_arguments(key, record, '')}),\n"
        for key, record in sorted(roots.items())) + "]\n", encoding="utf-8")
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
        constants = {"OPS_ORIGIN":ops,"ARTIFACT_ORIGIN":artifact,"SILENT_PROFILE":profile}
        body = "package com.carriez.flutter_hbb;\n\nfinal class FleetBuild {\n"
        body += "".join("    static final String "+key+" = "+json.dumps(v)+";\n" for key,v in constants.items())
        body += "    static final FleetRoot[] ROOTS = {\n" + "".join(
            f"        new FleetRoot({root_arguments(key, record, 'L')}),\n"
            for key, record in sorted(roots.items())) + "    };\n    private FleetBuild() {}\n}\n"
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
