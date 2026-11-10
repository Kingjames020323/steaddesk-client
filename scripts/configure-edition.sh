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
