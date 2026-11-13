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
import shutil
from pathlib import Path
import sys

tree = Path(sys.argv[1])
merchant = sys.argv[2] == "false"
phone = os.environ.get("STEADDESK_SUPPORT_PHONE", "").strip() if merchant else ""
def dart_string(value):
    return json.dumps(value, ensure_ascii=True).replace("$", r"\$")

(tree / "flutter/lib/steaddesk/merchant_build.dart").write_text(
    "const merchantEdition = " + str(merchant).lower() + ";\n"
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
    start = "    <application"
    if base.count(start) != 1:
        raise ValueError("Unexpected merchant manifest")
    permissions = ("REQUEST_INSTALL_PACKAGES", "UPDATE_PACKAGES_WITHOUT_USER_ACTION")
    base = base.replace(start, "".join(
        f'    <uses-permission android:name="android.permission.{name}" />\n'
        for name in permissions) + start)
    end = "    </application>"
    if base.count(end) != 1:
        raise ValueError("Unexpected Android main manifest")
    manifest.write_text(base.replace(end, (assets / "provider.xml").read_text(encoding="utf-8") + end), encoding="utf-8")
PY
