"""Build-time merchant/default-off and fixed public-root gates."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE=Path(__file__).resolve().parents[1]/"configure-fleet.py"
spec=importlib.util.spec_from_file_location("configure_fleet",MODULE)
fleet=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fleet)

class FleetBuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tree=Path(self.tmp.name)
        (self.tree/"RELEASE_VERSION").write_text("1.5.0-sd.12")
        (self.tree/"src").mkdir()
        self.app=self.tree/"flutter/android/app/src"
        manifest=self.app/"steaddeskStaging/AndroidManifest.xml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('<manifest>\n    <application>\n    </application>\n</manifest>\n')
    def configure(self,merchant=True,**env):
        with patch.dict(os.environ,env,clear=True):fleet.configure(self.tree,merchant)
    def test_default_has_no_updater_or_manifest_components(self):
        self.configure()
        self.assertEqual((self.tree/"src/steaddesk_fleet.rs").read_text(),"false\n")
        self.assertFalse((self.app/"steaddeskFleet").exists())
        self.assertNotIn("FleetReceiver",(self.app/"steaddeskStaging/AndroidManifest.xml").read_text())
        self.assertNotIn("UPDATE_PACKAGES_WITHOUT_USER_ACTION",(self.app/"steaddeskStaging/AndroidManifest.xml").read_text())
    def test_support_never_links_updater(self):
        self.configure(False,STEADDESK_FLEET_UPDATE="true")
        self.assertFalse((self.app/"steaddeskFleet").exists())
        self.assertNotIn("FleetUpdater",(self.app/"main/java/com/carriez/flutter_hbb/FleetEntry.java").read_text())
    def test_enabled_copies_fixed_root_and_actual_source(self):
        self.configure(STEADDESK_FLEET_UPDATE="1",STEADDESK_FLEET_OPS_ORIGIN="https://127.0.0.1:9443",STEADDESK_FLEET_TEST_PUBLIC_KEY="",STEADDESK_FLEET_TEST_KEY_ID="")
        java=self.app/"steaddeskFleet/java/com/carriez/flutter_hbb"
        self.assertTrue((java/"FleetRuntime.java").is_file())
        self.assertIn(fleet.DEFAULT_PUBLIC,(java/"FleetBuild.java").read_text())
        self.assertIn("FleetReceiver",(self.app/"steaddeskStaging/AndroidManifest.xml").read_text())
        self.assertIn("UPDATE_PACKAGES_WITHOUT_USER_ACTION",(self.app/"steaddeskStaging/AndroidManifest.xml").read_text())
    def test_invalid_origin_key_and_tag_are_rejected(self):
        base={"STEADDESK_FLEET_UPDATE":"1","STEADDESK_FLEET_OPS_ORIGIN":"https://localhost"}
        for env in ({"STEADDESK_FLEET_OPS_ORIGIN":"http://localhost"},{"STEADDESK_FLEET_OPS_ORIGIN":"https://user:secret@localhost"},{"STEADDESK_FLEET_OPS_ORIGIN":"https://localhost/path"},{"STEADDESK_FLEET_TEST_KEY_ID":"official-key"},{"STEADDESK_FLEET_TEST_PUBLIC_KEY":"invalid"},{"GITHUB_REF_TYPE":"tag"},{"STEADDESK_FLEET_SILENT_PROFILE":"arbitrary-label"}):
            with self.subTest(env=env),self.assertRaises(ValueError):self.configure(**(base|env))
    def test_missing_https_origin_does_not_build(self):
        with self.assertRaises(ValueError):self.configure(STEADDESK_FLEET_UPDATE="true")

    def test_windows_config_uses_its_own_profile_and_current_build(self):
        enabled = {"STEADDESK_FLEET_UPDATE": "true", "STEADDESK_FLEET_OPS_ORIGIN": "https://127.0.0.1"}
        self.configure(**enabled, STEADDESK_FLEET_WINDOWS_PROFILE="a" * 64, STEADDESK_FLEET_SILENT_PROFILE="b" * 64)
        config = self.tree / "src/steaddesk_fleet_windows_config.rs"
        self.assertIn("pub const CURRENT_BUILD: u64 = 12;", config.read_text())
        self.assertIn("a" * 64, config.read_text())
        self.assertNotIn("b" * 64, config.read_text())
        self.configure(merchant=False, **enabled)
        self.assertFalse(config.exists())
        with self.assertRaises(ValueError):
            self.configure(**enabled, STEADDESK_FLEET_WINDOWS_PROFILE="not-a-profile")
