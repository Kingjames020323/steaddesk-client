#!/usr/bin/env bash
# Select the native policy and Windows resource identity for a patched source tree.
set -euo pipefail
tree=${1:?expected a patched source directory}
case ${2:?expected merchant or support} in
  merchant) support=false; product=SteadDesk ;;
  support) support=true; product='SteadDesk Support' ;;
  *) echo 'Edition must be merchant or support' >&2; exit 2 ;;
esac
printf '%s\n' "$support" > "$tree/libs/hbb_common/src/steaddesk_support.rs"
printf '#define STEADDESK_PRODUCT "%s"\n' "$product" > "$tree/flutter/windows/runner/steaddesk_product.h"

# Compile the merchant UI with the same edition selector as the native policy.
mkdir -p "$tree/flutter/lib/steaddesk"
staging_assets=$(cd "$(dirname "$0")/../android-staging" && pwd)
python3 - "$tree" "$support" "$staging_assets" <<'PY'
import json
import os
import re
import shutil
from pathlib import Path
import sys

tree = Path(sys.argv[1])
merchant = sys.argv[2] == "false"
phone = os.environ.get("STEADDESK_SUPPORT_PHONE", "").strip() if merchant else ""
cases = os.environ.get("STEADDESK_CASES", "").strip().lower()
if cases not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_CASES must be true, false, 1 or 0")
cases = not merchant and cases in ("true", "1")
lib = tree / "flutter/lib/steaddesk"
# The merchant and disabled builds never import the case form or its storage.
for name in ("case_session", "case_inbox", "history_host"):
    source = name if cases else name + "_off"
    (lib / (name + "_api.dart")).write_text(
        f"export 'cases/{source}.dart';\n", encoding="utf-8")
def dart_string(value):
    return json.dumps(value, ensure_ascii=True).replace("$", r"\$")

(tree / "flutter/lib/steaddesk/merchant_build.dart").write_text(
    "const merchantEdition = " + str(merchant).lower() + ";\n"
    "const casesEnabled = " + str(cases).lower() + ";\n"
    "const merchantVersion = " + dart_string((tree / "RELEASE_VERSION").read_text().strip()) + ";\n"
    "const merchantPhone = String.fromEnvironment('STEADDESK_SUPPORT_PHONE', defaultValue: "
    + dart_string(phone) + ");\n", encoding="utf-8")
# Keep the main manifest intact for the support build and the patch queue.
app = tree / "flutter/android/app/src"
assets = Path(sys.argv[3])
out = app / "steaddeskStaging"
manifest = out / "AndroidManifest.xml"
sources = sorted((assets / "src/main/java").rglob("*.java"))
for source in sources:
    dest = out / source.relative_to(assets / "src/main")
    if not merchant:
        dest.unlink(missing_ok=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
if not merchant:
    manifest.unlink(missing_ok=True)
else:
    base = (app / "main/AndroidManifest.xml").read_text(encoding="utf-8")
    cert = os.environ.get("STEADDESK_AGENT_CERT_SHA256", "").strip().upper()
    if cert and not re.fullmatch(r"[0-9A-F]{64}", cert):
        raise ValueError("Expected 64 hex digits for STEADDESK_AGENT_CERT_SHA256")
    recovery = (assets / "recovery-manifest.xml").read_text(encoding="utf-8")
    recovery = recovery.replace("__AGENT_CERT__", cert or "@null").replace(
        "__WAKE_PROTECTION__", "signature|knownSigner" if cert else "signature")
    if base.count("<queries>") != 1:
        raise ValueError("Expected one queries section")
    base = base.replace("<queries>", recovery + '\n    <queries>\n        <package android:name="com.steaddesk.agent" />')
    # Only the merchant receiver resumes service after an in-place update.
    boot = '<action android:name="android.intent.action.BOOT_COMPLETED" />'
    if base.count(boot) != 1:
        raise ValueError("Expected a single Android boot action")
    base = base.replace(boot, boot + '\n                <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />')
    end = "    </application>"
    if base.count(end) != 1:
        raise ValueError("Unexpected Android main manifest")
    manifest.write_text(base.replace(end, (assets / "provider.xml").read_text(encoding="utf-8") + end), encoding="utf-8")
PY
