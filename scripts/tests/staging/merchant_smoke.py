"""Test the CI merchant APK on a disposable AOSP emulator, with no UI launch."""
import base64
import hashlib
import hmac
import secrets
import sys
import tomllib
import xml.etree.ElementTree as ET

from nacl.secret import SecretBox

from check_provider import adb, expect_status, shell, write

MERCHANT = "com.steaddesk.remote"
AUTHORITY = MERCHANT + ".staging"
CONFIG = f"/data/user/0/{MERCHANT}/app_flutter/SteadDesk.toml"
ALPHABET = b"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def check_manifest(path):
    manifest = ET.parse(path).getroot()
    android = "{http://schemas.android.com/apk/res/android}"
    assert manifest.get("package") == MERCHANT, "Wrong edition package"
    providers = [p for p in manifest.findall("./application/provider")
                 if p.get(android + "authorities") == AUTHORITY]
    assert len(providers) == 1, "Expected one merchant staging provider"
    provider = providers[0]
    assert provider.get(android + "name") == AUTHORITY + ".StagingPasswordProvider"
    assert provider.get(android + "exported") == "true"
    assert provider.get(android + "grantUriPermissions", "false") == "false"
    assert not list(provider), "Unexpected staging provider routes or grants"


def verify_saved(expected):
    # Independent check against the pinned hbb_common config/permanent_password.rs
    # and password_security.rs formats, using only this disposable emulator's config.
    # The config and all crypto material stay in memory and out of diagnostics.
    try:
        config = tomllib.loads(shell("su", "0", "cat", CONFIG))
        assert config["salt"] and config["password"].startswith("01")
        blob = base64.b64decode(config["password"][2:], validate=True)
        assert blob[0] == 1
        public_key = bytes(config["key_pair"][1])
        actual = SecretBox(public_key).decrypt(blob[1:])
        digest = hashlib.sha256(expected + config["salt"].encode()).digest()
        assert hmac.compare_digest(actual, b"00" + base64.b64encode(digest))
    except Exception:
        raise SystemExit("Persisted merchant credential verification failed") from None


def main():
    check_manifest(sys.argv[2])
    packages = shell("pm", "list", "packages", MERCHANT).splitlines()
    if f"package:{MERCHANT}" in packages:
        raise SystemExit("Merchant app already installed on the selected emulator")
    first = bytes(secrets.choice(ALPHABET) for _ in range(20))
    replacement = bytes(secrets.choice(ALPHABET) for _ in range(20))
    assert first != replacement
    adb("install", sys.argv[1])
    try:
        expect_status(False)
        write(first)
        expect_status(True)
        shell("am", "force-stop", MERCHANT)
        expect_status(True)
        verify_saved(first)
        write(first[:19])
        expect_status(False)
        shell("am", "force-stop", MERCHANT)
        expect_status(False)
        verify_saved(first)
        write(replacement + b"\n")
        expect_status(True)
        shell("am", "force-stop", MERCHANT)
        expect_status(True)
        verify_saved(replacement)
        print("PASS assembled merchant APK cold write, invalid rotation and replacement after restart")
    finally:
        adb("uninstall", MERCHANT)


if __name__ == "__main__":
    main()
