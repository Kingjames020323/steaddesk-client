#!/usr/bin/env python3
"""Check the merchant UI in a patched RustDesk tree. --table prints the review copy."""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

LANGUAGES = ("en", "zh", "es")
TEXT = r'"(?:[^"\\]|\\.)*"'
PAIR = re.compile(r'\(\s*(' + TEXT + r')\s*,\s*(' + TEXT + r')\s*,?\s*\)')
# These keys also come from shared dialogs, nested widgets and Rust's tray menu.
MANIFEST = Path(__file__).with_name("merchant-language-keys.json")


def rust_catalog(path):
    return {json.loads(k): json.loads(v) for k, v in PAIR.findall(path.read_text())}


def android_catalog(app, suffix):
    result = {}
    for source_set in ("main", "steaddeskMerchant"):
        for path in sorted((app / source_set / "res" / ("values" + suffix)).glob("*.xml")):
            for item in ET.parse(path).getroot().findall("string"):
                value = "".join(item.itertext()).replace(r'\"', '"').replace(r"\'", "'")
                result[item.attrib["name"]] = value
    return result


def android_uses(app):
    refs = set()
    for folder in ("main", "steaddeskMerchant"):
        for path in (app / folder).rglob("*"):
            if path.suffix in {".java", ".kt", ".xml"}:
                refs.update(re.findall(r"(?<!android\.)(?:\bR\.string\.|@string/)(\w+)", path.read_text()))
    return refs


def panel_keys(text):
    # Includes permissions and status strings passed through conditional expressions.
    keys = set()
    for call in re.finditer(r"\b(?:translate|permission|label)\(\s*", text):
        rest = text[call.end():]
        first = re.match(r"""['"]([^'"]*)['"]""", rest)
        if first:
            keys.add(first[1])
        elif text[call.start():].startswith("translate("):
            # Nested ternary strings occur inside the first argument; end it at
            # its matching parenthesis so a later widget cannot contribute keys.
            depth = 1
            expr = []
            for token in re.finditer(r"""'([^']*)'|"([^"]*)"|[()]""", rest):
                if token[0] == "(":
                    depth += 1
                elif token[0] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                else:
                    expr.append(token[1] if token[1] is not None else token[2])
            keys.update(expr)
    return {re.sub(r"\{\$\w+\}", "{}", k) for k in keys}


def rows_for(source):
    groups = json.loads(MANIFEST.read_text())
    catalogs = {language: rust_catalog(source / "src/lang" / (name + ".rs"))
                for language, name in zip(LANGUAGES, ("en", "cn", "es"))}
    app = source / "flutter/android/app/src"
    native = {lang: android_catalog(app, suffix)
              for lang, suffix in zip(LANGUAGES, ("", "-zh", "-es"))}
    panel = (source / "flutter/lib/steaddesk/merchant_panel.dart").read_text()
    declared = {key for keys in groups.values() for key in keys}
    rows = {}
    errors = []

    def add(key):
        values = []
        for language in LANGUAGES:
            # RustDesk uses literal English keys if there is no English override.
            fallback = key if language == "en" and "_" not in key else ""
            value = catalogs[language].get(key, fallback)
            if not value.strip():
                errors.append(f"src/lang: {language}: missing {key!r}")
            elif value.count("{}") != key.count("{}"):
                errors.append(f"src/lang: {language}: placeholder mismatch in {key!r}")
            values.append(value)
        rows[key] = values
        return values

    for key in sorted(panel_keys(panel) - declared):
        errors.append(f"merchant panel: undocumented key {key!r}")
    for keys in groups.values():
        for key in keys:
            add(key)

    # Check the union so removing a default AND its translations still fails
    # when code, a manifest or an Android restriction references the resource.
    for resource in sorted(android_uses(app).union(*(set(table) for table in native.values()))):
        values = [native[lang].get(resource, "") for lang in LANGUAGES]
        for lang, value in zip(LANGUAGES, values):
            if not value.strip():
                errors.append(f"Android: {lang}: missing {resource}")
        if values[0] and add(values[0]) != values:
            errors.append(f"Android: {resource} differs from the Rust language table")
    if errors:
        raise ValueError("\n".join(errors))
    return rows


def markdown(text):
    return text.replace("RustDesk", "SteadDesk").replace("|", r"\|").replace("\n", "<br>")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--table", action="store_true")
    args = parser.parse_args()
    try:
        rows = rows_for(args.source)
    except ValueError as err:
        sys.exit(str(err))
    if args.table:
        print("| 中文 | English | Español |\n|---|---|---|")
        for en, zh, es in rows.values():
            print("| " + " | ".join(map(markdown, (zh, en, es))) + " |")
    else:
        print(f"{len(rows)} merchant strings checked in English, Chinese and Spanish")
