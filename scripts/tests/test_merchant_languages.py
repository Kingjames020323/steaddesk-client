"""Prevent manifest-only exclusions from weakening normal merchant translations."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "check-merchant-languages.py"
SPEC = importlib.util.spec_from_file_location("merchant_languages", SCRIPT)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class MerchantLanguagesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "keys.json"
        self.manifest.write_text(json.dumps({"panel": ["Ready"]}))
        manifest_patch = patch.object(CHECK, "MANIFEST", self.manifest)
        manifest_patch.start()
        self.addCleanup(manifest_patch.stop)
        for lang, translation in (("en", "Ready"), ("cn", "就绪"), ("es", "Listo")):
            self.write(f"src/lang/{lang}.rs", f'("Ready", "{translation}")')
        self.write("flutter/lib/steaddesk/merchant_panel.dart", "Text(translate('Ready'))")
        for suffix, value in (("", "Ready"), ("-zh", "就绪"), ("-es", "Listo")):
            self.write(self.resource(suffix), f'<resources><string name="status">{value}</string></resources>')
        self.write("flutter/android/app/src/main/AndroidManifest.xml",
                   '<manifest><meta-data value="@string/subtype"/></manifest>')
        self.write("flutter/android/app/src/main/res/values/manifest.xml",
                   '<resources><string name="subtype" translatable="false">Service metadata</string></resources>')

    def write(self, path, value):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(value)

    def resource(self, suffix):
        return f"flutter/android/app/src/main/res/values{suffix}/strings.xml"

    def test_non_translatable_metadata_needs_no_rust_or_locale_entry(self):
        self.assertEqual(CHECK.rows_for(self.root), {"Ready": ["Ready", "就绪", "Listo"]})

    def test_regular_translation_is_still_required(self):
        self.write(self.resource("-es"), "<resources/>")
        with self.assertRaisesRegex(ValueError, "es: missing status"):
            CHECK.rows_for(self.root)

    def test_non_translatable_translation_is_rejected(self):
        self.write("flutter/android/app/src/steaddeskMerchant/res/values-es/metadata.xml",
                   '<resources><string name="subtype">Metadatos</string></resources>')
        with self.assertRaisesRegex(ValueError, "non-translatable resource subtype has a translation"):
            CHECK.rows_for(self.root)

    def test_missing_default_cannot_be_exempted_by_locale_attribute(self):
        (self.root / "flutter/android/app/src/main/res/values/manifest.xml").unlink()
        self.write("flutter/android/app/src/steaddeskMerchant/res/values-es/metadata.xml",
                   '<resources><string name="subtype" translatable="false">Metadatos</string></resources>')
        with self.assertRaisesRegex(ValueError, "en: missing subtype"):
            CHECK.rows_for(self.root)
