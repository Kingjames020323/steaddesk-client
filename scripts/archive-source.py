#!/usr/bin/env python3
"""Archive a public SteadDesk release from an initialized recursive checkout.

Run before building: python3 scripts/archive-source.py OUTPUT.tar.gz
The wrapper's HEAD and its gitlinks select every input. Patching happens in a
temporary checkout, so a developer's local edits and build outputs stay out.
Requires Python 3.9+, Bash and Git with git archive --mtime.
"""
import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


PRIVATE_HEADER = re.compile(
    rb"(?m)^\s*(?:-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----"
    rb"|PuTTY-User-Key-File-[23]:)"
)
KEY_SUFFIXES = {".jks", ".keystore", ".p12", ".pfx", ".pem", ".key", ".ppk", ".kdbx"}
KEY_NAMES = {"id_rsa", "id_dsa", "id_ed25519", "id_ecdsa", "key.properties", ".env"}


def git(repo, *args):
    return subprocess.check_output(["git", "-C", repo, *args])


def gitlinks(repo, revision):
    links = {}
    for entry in git(repo, "ls-tree", "-rz", revision).split(b"\0"):
        if entry.startswith(b"160000 commit "):
            metadata, name = entry.split(b"\t", 1)
            links[Path(os.fsdecode(name))] = metadata.split()[2].decode("ascii")
    return links


def clone_pinned(source, dest, revision):
    if not (source / ".git").exists():
        raise ValueError(f"initialize recursive submodule checkout at {source}")
    head = git(source, "rev-parse", "HEAD").decode().strip()
    if head != revision:
        raise ValueError(f"gitlink mismatch at {source}: expected {revision}, found {head}")
    # Read Git objects from the public checkout. Nothing from its working tree
    # is copied, including ignored build products and untracked credentials.
    git(source, "clone", "-q", "--template=", "--shared", "--no-checkout", "--", source, dest)
    git(dest, "-c", "core.autocrlf=false", "checkout", "-q", "--detach", revision)
    repos = [dest]
    for path, commit in gitlinks(dest, revision).items():
        repos.extend(clone_pinned(source / path, dest / path, commit))
    return repos


def check_inputs(tree):
    for path in tree.rglob("*"):
        if path.name == ".git":
            raise ValueError(f"unexpected Git metadata at {path.relative_to(tree)}")
        if path.name.lower() in KEY_NAMES or path.suffix.lower() in KEY_SUFFIXES:
            raise ValueError(f"excluded credential filename: {path.relative_to(tree)}")
        if path.is_symlink():
            if os.path.isabs(os.readlink(path)) or not path.resolve().is_relative_to(tree):
                raise ValueError(f"external symlink: {path.relative_to(tree)}")
        elif path.is_file() and PRIVATE_HEADER.search(path.read_bytes()):
            raise ValueError(f"private key marker: {path.relative_to(tree)}")


def archive(source, output):
    head = git(source, "rev-parse", "HEAD").decode().strip()
    if set(gitlinks(source, head)) != {Path("upstream")}:
        raise ValueError("expected the public wrapper with one upstream gitlink")
    epoch = git(source, "show", "-s", "--format=%ct", head).decode().strip()
    with tempfile.TemporaryDirectory() as scratch:
        tree = Path(scratch).resolve() / "source"
        repos = clone_pinned(source, tree, head)
        version = (tree / "RELEASE_VERSION").read_text().strip()
        release = re.fullmatch(r"1\.5\.0-sd\.([1-9][0-9]{0,4})", version)
        if not release or int(release[1]) > 65535:
            raise ValueError("invalid RELEASE_VERSION")
        subprocess.run(["bash", tree / "scripts/apply-patches.sh", tree / "upstream"],
                       cwd=tree, check=True)
        for repo in repos:
            shutil.rmtree(repo / ".git")
        check_inputs(tree)

        # Flatten the patched checkout, including files created by the patch
        # step and modifications inside nested gitlinks. Only this disposable
        # tree ever enters the archive index.
        git(tree, "init", "-q", "--template=")
        (tree / ".git/info").mkdir(exist_ok=True)
        (tree / ".git/info/attributes").write_text(
            "* -export-ignore -export-subst -text -filter -ident -working-tree-encoding\n"
        )
        git(tree, "-c", "core.filemode=true", "add", "-f", "--all")
        snapshot = git(tree, "write-tree").decode().strip()
        # Keep an existing bundle intact if git archive or the filesystem fails.
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temp:
            partial = Path(temp.name)
        try:
            git(tree, "-c", "tar.umask=0022", "archive", "--format=tar.gz",
                f"--mtime=@{epoch}", f"--prefix=SteadDesk-{version}-source/",
                f"--output={partial}", snapshot)
            os.replace(partial, output)
        finally:
            partial.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="destination .tar.gz (existing directory)")
    try:
        archive(Path(__file__).resolve().parents[1], parser.parse_args().output.resolve())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"source archive failed: {error}\n")
