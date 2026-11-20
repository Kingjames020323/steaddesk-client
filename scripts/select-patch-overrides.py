"""Materialize the per-file patch variant for coexisting independent PRs."""
from pathlib import Path
import re
import sys


SECTION = re.compile(rb"^diff --git a/(\S+) b/\1\r?$", re.M)


def sections(data):
    matches = list(SECTION.finditer(data))
    if not matches or len(matches) != len(re.findall(rb"^diff --git ", data, re.M)):
        raise ValueError("expected a same-path Git patch")
    result = {}
    for i, match in enumerate(matches):
        path = match[1]
        if path in result:
            raise ValueError(f"duplicate diff for {path!r}")
        end = matches[i + 1].start() if i + 1 < len(matches) else len(data)
        result[path] = data[match.start():end]
    return data[:matches[0].start()], result


def select(queue, output):
    patches = {p.name.split("-", 1)[0]: p for p in queue.glob("*.patch")}
    replacements = {}
    for variant in sorted((queue / "compat").glob("*.override.patch")):
        required, target, _ = variant.name.split("-", 2)
        if target not in patches or not set(required.split("+")).issubset(patches):
            continue
        _, edits = sections(variant.read_bytes())
        target_edits = replacements.setdefault(target, {})
        if edits.keys() & target_edits.keys():
            raise ValueError(f"ambiguous file override for {variant.name}")
        target_edits.update(edits)
    for number, edits in replacements.items():
        patch = patches[number]
        header, original = sections(patch.read_bytes())
        if not edits.keys() <= original.keys():
            raise ValueError(f"override adds an unrelated file to {patch.name}")
        original.update(edits)
        (output / patch.name).write_bytes(header + b"".join(original.values()))


if __name__ == "__main__":
    select(Path(sys.argv[1]), Path(sys.argv[2]))
