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
python3 - "$tree" "$support" <<'PY'
import json
import os
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
PY
