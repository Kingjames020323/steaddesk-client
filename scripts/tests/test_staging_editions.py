"""Check edition selection when a build tree is reused in either direction."""
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = "{http://schemas.android.com/apk/res/android}"
AUTHORITY = "com.steaddesk.remote.staging"


class StagingEditionTests(unittest.TestCase):
    def test_merchant_support_merchant(self):
        with tempfile.TemporaryDirectory() as temp:
            tree = Path(temp)
            app = tree / "flutter/android/app/src"
            for directory in ("libs/hbb_common/src", "flutter/windows/runner", "flutter/android/app/src/main"):
                (tree / directory).mkdir(parents=True)
            (tree / "RELEASE_VERSION").write_text("1.5.0-sd.1")
            main = app / "main/AndroidManifest.xml"
            original = ('<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
                        '    <application><service android:name=".MainService"/>\n'
                        '<receiver android:name=".BootReceiver"><intent-filter>'
                        '<action android:name="android.intent.action.BOOT_COMPLETED" />'
                        '</intent-filter></receiver>\n'
                        '    </application>\n</manifest>')
            main.write_text(original)
            assets = app / "steaddeskStaging"
            manifest = assets / "AndroidManifest.xml"
            for edition in ("merchant", "support", "merchant"):
                with self.subTest(edition=edition):
                    subprocess.run(["bash", ROOT / "scripts/configure-edition.sh", tree, edition], check=True)
                    self.assertEqual(main.read_text(), original)
                    merchant = edition == "merchant"
                    self.assertEqual(manifest.exists(), merchant)
                    classes = sorted(p.name for p in assets.rglob("*.java"))
                    self.assertEqual(classes, ["StagingPasswordProvider.java", "StagingPasswords.java"] if merchant else [])
                    selected = ET.parse(manifest if merchant else main)
                    self.assertIsNotNone(selected.find("application/service"))
                    receiver = selected.find(f"application/receiver[@{ANDROID}name='.BootReceiver']")
                    self.assertIsNotNone(receiver)
                    actions = receiver.findall("intent-filter/action")
                    self.assertEqual([a.attrib[ANDROID + "name"] for a in actions],
                                     ["android.intent.action.BOOT_COMPLETED"] +
                                     (["android.intent.action.MY_PACKAGE_REPLACED"] if merchant else []))
                    providers = selected.findall("application/provider")
                    self.assertEqual(len(providers), int(merchant))
                    if merchant:
                        self.assertEqual(providers[0].attrib, {
                            ANDROID + "authorities": AUTHORITY,
                            ANDROID + "name": AUTHORITY + ".StagingPasswordProvider",
                            ANDROID + "exported": "true", ANDROID + "grantUriPermissions": "false",
                        })
                        self.assertEqual(list(providers[0]), [])
