#!/usr/bin/env bash
set -euo pipefail
# Later patches may edit lines introduced by earlier ones. Rewind the applied
# prefix in a disposable index, then preflight the entire queue before writing.
patch_dir=${1:?expected a patch directory}
if (( $# > 1 )); then
  # apply-patches.sh passes the initialized scratch index and its ordered queue.
  scratch=$2
  shift 2
  patches=("$@")
else
  patches=("$patch_dir"/*.patch)
  scratch=$(mktemp -d)
  trap 'rm -r -- "$scratch"' EXIT
  git init -q "$scratch"
fi
while IFS= read -r -d '' record; do
  path=${record#*$'\t'}
  path=${path#*$'\t'}
  [[ -f $path ]] || continue
  mode=100644
  if [[ -x $path ]]; then mode=100755; fi
  blob=$(git -C "$scratch" hash-object -w --stdin < "$path")
  git -C "$scratch" update-index --add --cacheinfo "$mode,$blob,$path"
done < <(git apply --numstat -z "${patches[@]}")
# U-04b also replaces U-04's legacy remote shortcuts. Stacked branches
# without U-04 have no such renderer; all device-side hunks always apply.
apply_patch_in() {
  local tree=$1 patch=$2
  shift 2
  if [[ ${patch##*/} == 0017-android-file-scope.patch && ! -f "$patch_dir/0013-file-transfer.patch" ]]; then
    git -C "$tree" apply --exclude=flutter/lib/steaddesk/file_transfer.dart "$@" "$patch"
  else
    git -C "$tree" apply "$@" "$patch"
  fi
}

# Edition configuration owns these complete generated files. They were all
# introduced as new files by the queue; none exists in the pinned upstream.
# Match exact renderer outputs before treating any path as generated.
python3 "$(dirname "$0")/edition_selectors.py" "$PWD" > "$scratch/selectors"
omit=()
while IFS= read -r path; do
  if git -C "$scratch" ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
    git -C "$scratch" update-index --force-remove -- "$path"
    omit+=("--exclude=$path")
  fi
done < "$scratch/selectors"

applied=0
for ((i=${#patches[@]}-1; i>=0; i--)); do
  patch=${patches[i]}
  if (( ${#omit[@]} )) && [[ -z $(apply_patch_in "$scratch" "$patch" --numstat "${omit[@]}") ]]; then
    continue  # Its entire output is regenerated; still check the full patch below.
  fi
  if apply_patch_in "$scratch" "$patch" --cached --reverse ${omit[@]+"${omit[@]}"} 2>/dev/null; then
    if ((applied == 0)); then applied=$((i+1)); fi
  elif ((applied != 0)); then
    echo "Inconsistent patch queue at ${patch##*/}" >&2
    exit 1
  fi
done
# Check every hunk against its raw pre-configuration input, including selectors.
for patch in "${patches[@]}"; do apply_patch_in "$scratch" "$patch" --cached; done
for ((i=applied; i<${#patches[@]}; i++)); do
  apply_patch_in "$PWD" "${patches[i]}" ${omit[@]+"${omit[@]}"}
done
