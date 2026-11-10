"""Prepare and atomically publish a local release bundle for the signing scripts."""

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path


MANIFEST = "SHA256SUMS"
ASSET = re.compile(
    r"(SteadDesk-[0-9]+\.[0-9]+\.[0-9]+-sd\.[1-9][0-9]*)-"
    r"(x64(?:\.unsigned)?\.exe|universal(?:\.unsigned)?\.apk|source\.tar\.gz)"
)
ENTRY = re.compile(r"([a-fA-F0-9]{64}) [ *](.+)")
UNSIGNED = {"windows": "x64.unsigned.exe", "android": "universal.unsigned.apk"}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inspect_bundle(directory, platform):
    manifest = directory / MANIFEST
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Missing regular SHA256SUMS")
    hashes = {}
    types = set()
    prefixes = set()
    unsigned = None
    for line in manifest.read_text(encoding="ascii").splitlines():
        entry = ENTRY.fullmatch(line)
        asset = ASSET.fullmatch(entry[2]) if entry else None
        if not asset:
            raise ValueError("Invalid release manifest entry")
        name = entry[2]
        prefixes.add(asset[1])
        kind = asset[2].replace(".unsigned.", ".")
        if kind in types:
            raise ValueError(f"Duplicate release asset type: {kind}")
        types.add(kind)
        hashes[name] = entry[1].lower()
        if asset[2] == UNSIGNED[platform]:
            unsigned = name
    if len(prefixes) != 1 or types != {"x64.exe", "universal.apk", "source.tar.gz"}:
        raise ValueError("Expected one version with Windows, Android and source assets")
    if not unsigned:
        raise ValueError(f"Missing unsigned {platform} input")
    if {item.name for item in directory.iterdir()} != set(hashes) | {MANIFEST}:
        raise ValueError("Release directory and SHA256SUMS contain different entries")
    for name in hashes:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Expected a regular asset: {name}")
    return unsigned, hashes


def write_manifest(directory, hashes):
    with (directory / MANIFEST).open("w", encoding="ascii", newline="\n") as stream:
        for name in sorted(hashes):
            stream.write(f"{hashes[name]}  {name}\n")


def prepare(source, scratch, platform):
    unsigned, hashes = inspect_bundle(source, platform)
    bundle = scratch / "bundle"
    bundle.mkdir()
    for name, expected in hashes.items():
        staged = bundle / name
        shutil.copyfile(source / name, staged)
        if digest(staged) != expected:
            raise ValueError(f"Input checksum mismatch: {name}")
    write_manifest(bundle, hashes)
    print(unsigned)


def publish(scratch, output, platform):
    bundle = scratch / "bundle"
    unsigned, hashes = inspect_bundle(bundle, platform)
    signed = unsigned.replace(".unsigned.", ".")
    verified = scratch / signed
    if verified.is_symlink() or not verified.is_file() or verified.stat().st_size == 0:
        raise ValueError("Missing verified signing output")
    signed_hash = digest(verified)
    if signed_hash == hashes.pop(unsigned):
        raise ValueError("Signing left the unsigned input unchanged")
    for name, expected in hashes.items():
        if digest(bundle / name) != expected:
            raise ValueError(f"Staged asset checksum mismatch: {name}")
    (bundle / unsigned).unlink()
    verified.rename(bundle / signed)
    hashes[signed] = signed_hash
    write_manifest(bundle, hashes)
    if output.exists() or output.is_symlink():
        raise ValueError("Output directory already exists")
    # The wrappers create scratch next to output. Rename makes all four files visible together.
    bundle.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "publish"))
    parser.add_argument("platform", choices=UNSIGNED)
    parser.add_argument("source", type=Path, help="release directory or scratch directory")
    parser.add_argument("target", type=Path, help="scratch directory or new output directory")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            prepare(args.source, args.target, args.platform)
        else:
            publish(args.source, args.target, args.platform)
    except (OSError, ValueError) as error:
        sys.exit(str(error))
