"""Check edition selection when a build tree is reused in either direction."""
import os
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
                        '    <queries></queries>\n'
                        '    <application><service android:name=".MainService"/>\n'
                        '<receiver android:name=".BootReceiver"><intent-filter>'
                        '<action android:name="android.intent.action.BOOT_COMPLETED" />'
                        '</intent-filter></receiver>\n'
                        '    </application>\n</manifest>')
            main.write_text(original)
            assets = app / "steaddeskStaging"
            manifest = assets / "AndroidManifest.xml"
            for edition, flag, enable, metrics in [
                ("support", "", False, ""), ("support", "true", True, "false"),
                ("merchant", "true", False, "true"), ("support", "false", False, "1"),
                ("merchant", "", False, ""),
            ]:
                with self.subTest(edition=edition, flag=flag, metrics=metrics):
                    subprocess.run(["bash", ROOT / "scripts/configure-edition.sh", tree, edition],
                                   env={**os.environ, "STEADDESK_CASES": flag,
                                        "STEADDESK_METRICS": metrics,
                                        "STEADDESK_QUALITY": metrics,
                                        "STEADDESK_AGENT_CERT_SHA256": "aa" * 32 if flag else ""}, check=True)
                    lib = tree / "flutter/lib/steaddesk"
                    self.assertIn(f"const casesEnabled = {str(enable).lower()};",
                                  (lib / "merchant_build.dart").read_text())
                    quality = edition == "support" and metrics != "false"
                    self.assertIn(f"const qualityEnabled = {str(quality).lower()};",
                                  (lib / "merchant_build.dart").read_text())
                    expected_metrics = "support_metrics" if edition == "support" and metrics != "false" else "support_metrics_off"
                    self.assertEqual((lib / "metrics_api.dart").read_text().strip(),
                                     f"export 'metrics/{expected_metrics}.dart';")
                    for name in ("case_session", "case_inbox", "history_host"):
                        target = name if enable else name + "_off"
                        self.assertEqual((lib / f"{name}_api.dart").read_text().strip(),
                                         f"export 'cases/{target}.dart';")
                    self.assertEqual(main.read_text(), original)
                    merchant = edition == "merchant"
                    self.assertEqual(manifest.exists(), merchant)
                    classes = sorted(p.name for p in assets.rglob("*.java"))
                    self.assertEqual(classes, ["StagingPasswordProvider.java", "StagingPasswords.java"] if merchant else [])
                    selected = ET.parse(manifest if merchant else main)
                    self.assertEqual(selected.find(f"queries/package[@{ANDROID}name='com.steaddesk.agent']") is not None, merchant)
                    wake = selected.find(f"application/service[@{ANDROID}name='com.carriez.flutter_hbb.AgentWakeService']")
                    permission = selected.find(f"permission[@{ANDROID}name='com.steaddesk.remote.permission.WAKE_SERVICE']")
                    marker = selected.find(f"application/receiver[@{ANDROID}name='com.carriez.flutter_hbb.MerchantRemotePaused']")
                    self.assertEqual(marker is not None, merchant)
                    if merchant:
                        self.assertEqual(marker.attrib[ANDROID + "enabled"], "false")
                        self.assertEqual(marker.attrib[ANDROID + "exported"], "false")
                        self.assertEqual(list(marker), [])
                    self.assertEqual(wake is not None, merchant)
                    self.assertEqual(permission is not None, merchant)
                    self.assertEqual(selected.find(f"uses-permission[@{ANDROID}name='com.steaddesk.agent.permission.WAKE_CONNECTION']") is not None, merchant)
                    if merchant:
                        self.assertEqual(wake.attrib[ANDROID + "permission"], permission.attrib[ANDROID + "name"])
                        self.assertEqual(wake.attrib[ANDROID + "exported"], "true")
                        self.assertEqual(permission.attrib[ANDROID + "protectionLevel"], "signature|knownSigner" if flag else "signature")
                        self.assertEqual(permission.attrib[ANDROID + "knownCerts"], "AA" * 32 if flag else "@null")
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
