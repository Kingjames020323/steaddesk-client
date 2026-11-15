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
today = os.environ.get("STEADDESK_TODAY", "").strip().lower()
if today not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_TODAY must be true, false, 1 or 0")
today_module = "host" if not merchant and today in ("1", "true") else "off"
(lib / "today_api.dart").write_text(f"export 'today/{today_module}.dart';\n", encoding="utf-8")
quick = os.environ.get("STEADDESK_QUICK_CHECK", "").strip().lower()
if quick not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_QUICK_CHECK must be true, false, 1 or 0")
quick_enabled = quick in ("true", "1")
for role in ("merchant", "support"):
    selected = role if quick_enabled and (role == "merchant") == merchant else role + "_off"
    (lib / f"quick_{role}_api.dart").write_text(f"export 'quick/{selected}.dart';\n", encoding="utf-8")
(tree / "src").mkdir(exist_ok=True)
(tree / "src/steaddesk_qc2.rs").write_text(str(quick_enabled and merchant).lower() + "\n", encoding="utf-8")
toolbar = os.environ.get("STEADDESK_TOOLBAR", "").strip().lower()
if toolbar not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_TOOLBAR must be true, false, 1 or 0")
toolbar_enabled = toolbar in ("true", "1")
fixed = os.environ.get("STEADDESK_TOOLBAR_ACTIONS", "").strip().lower()
if fixed not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_TOOLBAR_ACTIONS must be true, false, 1 or 0")
fixed_enabled = fixed in ("true", "1")
(lib / "fixed_build.dart").write_text(
    f"const fixedSupportEnabled = {str(fixed_enabled and not merchant).lower()};\n"
    f"const readToolbarEnabled = {str(toolbar_enabled and not merchant).lower()};\n", encoding="utf-8")
selected = "merchant" if fixed_enabled and merchant else "off"
(lib / "fixed_merchant_api.dart").write_text(f"export 'fixed/{selected}.dart';\n", encoding="utf-8")
(tree / "src/steaddesk_fixed_enabled.rs").write_text(str(fixed_enabled and merchant).lower() + "\n", encoding="utf-8")
fixed_java = tree / "flutter/android/app/src/main/java/com/carriez/flutter_hbb/FixedActionBuild.java"
fixed_java.parent.mkdir(parents=True, exist_ok=True)
fixed_java.write_text("package com.carriez.flutter_hbb;\nfinal class FixedActionBuild { static final boolean ENABLED = "
    + str(fixed_enabled and merchant).lower() + "; }\n", encoding="utf-8")
module = "host" if (toolbar_enabled or fixed_enabled) and not merchant else "off"
(lib / "toolbar_api.dart").write_text(f"export 'toolbar/{module}.dart';\n", encoding="utf-8")
(tree / "src/steaddesk_tb.rs").write_text(str(toolbar_enabled and merchant).lower() + "\n", encoding="utf-8")
fleet_admin = os.environ.get("STEADDESK_FLEET_ADMIN", "").strip().lower()
if fleet_admin not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_FLEET_ADMIN must be true, false, 1 or 0")
fleet_admin_enabled = not merchant and fleet_admin in ("true", "1")
fleet_module = "fleet_admin_host" if fleet_admin_enabled else "fleet_admin_off"
(lib / "fleet_admin_api.dart").write_text(f"export 'fleet/{fleet_module}.dart';\n", encoding="utf-8")
help_flag = os.environ.get("STEADDESK_HELP", "").strip().lower()
if help_flag not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_HELP must be true, false, 1 or 0")
callback = os.environ.get("STEADDESK_CALLBACK", "").strip().lower()
if callback not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_CALLBACK must be true, false, 1 or 0")
callback_enabled = callback in ("true", "1")
(lib / "callback_build.dart").write_text(
    f"const merchantCallbacksEnabled = {str(callback_enabled and merchant).lower()};\n"
    f"const supportCallbacksEnabled = {str(callback_enabled and not merchant).lower()};\n",
    encoding="utf-8")
kb = os.environ.get("STEADDESK_KB", "").strip().lower()
if kb not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_KB must be true, false, 1 or 0")
kb = kb in ("true", "1")
(lib / "kb_build.dart").write_text(
    f"const merchantKbEnabled = {str(kb and merchant).lower()};\n"
    f"const supportKbEnabled = {str(kb and not merchant).lower()};\n", encoding="utf-8")
editor = "admin_host" if kb and not merchant else "admin_off"
(lib / "kb_admin_api.dart").write_text(f"export 'kb/{editor}.dart';\n", encoding="utf-8")
# Merchant cards live in the help waiting room; the admin editor is independent.
help_enabled = help_flag in ("true", "1") or callback_enabled or (kb and merchant)
support_help = not merchant and help_enabled
module = "support_help_host" if support_help else "support_help_off"
(lib / "support_help_header_api.dart").write_text(f"export '{module}.dart';\n", encoding="utf-8")
merchant_help = "merchant_help_host" if merchant and help_enabled else "merchant_help_off"
(lib / "merchant_help_api.dart").write_text(f"export 'help/{merchant_help}.dart';\n", encoding="utf-8")
metrics = os.environ.get("STEADDESK_METRICS", "").strip().lower()
if metrics not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_METRICS must be true, false, 1 or 0")
enabled = not merchant and metrics not in ("0", "false")
quality = os.environ.get("STEADDESK_QUALITY", "").strip().lower()
if quality not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_QUALITY must be true, false, 1 or 0")
quality_enabled = not merchant and quality not in ("0", "false")
reconnect = os.environ.get("STEADDESK_RECONNECT", "").strip().lower()
if reconnect not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_RECONNECT must be true, false, 1 or 0")
reconnect_enabled = not merchant and reconnect not in ("0", "false")
ops_groups = os.environ.get("STEADDESK_OPS_GROUPS", "").strip().lower()
if ops_groups not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_OPS_GROUPS must be true, false, 1 or 0")
ops_groups_enabled = not merchant and ops_groups in ("true", "1")
ops_health = os.environ.get("STEADDESK_OPS_HEALTH", "").strip().lower()
if ops_health not in ("", "0", "1", "false", "true"):
    raise ValueError("STEADDESK_OPS_HEALTH must be true, false, 1 or 0")
ops_health_enabled = not merchant and ops_health in ("true", "1")
module = "support_metrics" if enabled else "support_metrics_off"
(lib / "metrics_api.dart").write_text(f"export 'metrics/{module}.dart';\n", encoding="utf-8")
# The merchant and disabled builds never import the case form or its storage.
for name in ("case_session", "case_inbox", "history_host"):
    source = name if cases or support_help else name + "_off"
    (lib / (name + "_api.dart")).write_text(
        f"export 'cases/{source}.dart';\n", encoding="utf-8")
def dart_string(value):
    return json.dumps(value, ensure_ascii=True).replace("$", r"\$")

(tree / "flutter/lib/steaddesk/merchant_build.dart").write_text(
    "const merchantEdition = " + str(merchant).lower() + ";\n"
    "const fleetAdminEnabled = " + str(fleet_admin_enabled).lower() + ";\n"
    "const helpEnabled = " + str(help_enabled).lower() + ";\n"
    "const opsHealthEnabled = " + str(ops_health_enabled).lower() + ";\n"
    "const opsGroupsEnabled = " + str(ops_groups_enabled).lower() + ";\n"
    "const qualityEnabled = " + str(quality_enabled).lower() + ";\n"
    "const reconnectEnabled = " + str(reconnect_enabled).lower() + ";\n"
    "const normalCasesEnabled = " + str(cases).lower() + ";\n"
    "const casesEnabled = " + str(cases or support_help).lower() + ";\n"
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
python3 "$(dirname "$0")/configure-fleet.py" "$tree" "$2"
