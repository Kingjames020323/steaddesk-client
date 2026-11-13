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
                    self.assertEqual(classes, ["SelfUpdateProvider.java", "StagingPasswordProvider.java",
                                               "StagingPasswords.java", "UpdateReceiver.java"] if merchant else [])
                    selected = ET.parse(manifest if merchant else main)
                    self.assertIsNotNone(selected.find("application/service"))
                    providers = selected.findall("application/provider")
                    self.assertEqual(len(providers), 2 if merchant else 0)
                    permissions = {p.get(ANDROID + "name") for p in selected.findall("uses-permission")}
                    self.assertEqual(permissions, {
                        "android.permission.REQUEST_INSTALL_PACKAGES",
                        "android.permission.UPDATE_PACKAGES_WITHOUT_USER_ACTION",
                    } if merchant else set())
                    actions = selected.findall("application/receiver/intent-filter/action")
                    self.assertEqual([a.get(ANDROID + "name") for a in actions],
                                     ["android.intent.action.MY_PACKAGE_REPLACED"] if merchant else [])
                    if merchant:
                        self.assertEqual(selected.find("application/receiver").get(ANDROID + "exported"), "false")
                        self.assertEqual(providers[1].attrib, {
                            ANDROID + "authorities": "com.steaddesk.remote.spike",
                            ANDROID + "name": "com.steaddesk.remote.spike.SelfUpdateProvider",
                            ANDROID + "exported": "true", ANDROID + "grantUriPermissions": "false",
                        })
                    if merchant:
                        self.assertEqual(providers[0].attrib, {
                            ANDROID + "authorities": AUTHORITY,
                            ANDROID + "name": AUTHORITY + ".StagingPasswordProvider",
                            ANDROID + "exported": "true", ANDROID + "grantUriPermissions": "false",
                        })
                        self.assertEqual(list(providers[0]), [])
