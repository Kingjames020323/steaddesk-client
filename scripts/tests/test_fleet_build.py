"""Build-time merchant/default-off and fixed public-root gates."""
import base64
import importlib.util
import json
import os
import re
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

    def test_public_keyring_modes_overlap_alias_revocation_and_shape(self):
        # Public RFC 8032 test vectors. These values are fixtures only.
        old = base64.b64encode(bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")).decode()
        new = base64.b64encode(bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")).decode()
        record = dict(public_key=old, valid_from=1, valid_until=99, revoked=False)
        next_record = dict(record, public_key=new, valid_from=10, valid_until=200)
        ring = {"fixture-old": record, "fixture-next": next_record}
        env = dict(STEADDESK_FLEET_UPDATE="true", STEADDESK_FLEET_OPS_ORIGIN="https://example.invalid")
        def build(ring_text, tagged=True):
            self.configure(**env, GITHUB_REF_TYPE="tag" if tagged else "branch",
                           STEADDESK_FLEET_KEYRING=ring_text)
        encoded = json.dumps(ring)
        build(encoded.ljust(32768))
        with self.assertRaises(ValueError):
            build(encoded.ljust(32769))
        roots = self.tree / "src/steaddesk_fleet_key.rs"
        for public in [old, new]:
            self.assertIn(public, roots.read_text())
        for tagged, bad in [
            (False, ring), (False, {"test-a": record, **ring}),
            (True, {"test-a": record, **ring}), (True, {"test-a": record}),
            (True, {}), (True, {"fixture": dict(record, public_key="A" * 43 + "=")}),
            (True, {"fixture": dict(record, public_key=old[:-2] + "B=")}),
            (True, {"fixture": dict(record, public_key=fleet.DEFAULT_PUBLIC)}),
            (True, {"fixture": dict(record, valid_from=True)}),
            (True, {"fixture": dict(record, valid_until=1)}),
            (True, {"fixture": dict(record, revoked=0)}),
            (True, {"fixture": dict(record, extra="unexpected")}),
            (True, {"bad key": record}),
        ]:
            with self.subTest(tagged=tagged,bad=bad), self.assertRaises(ValueError):
                build(json.dumps(bad), tagged)
        with self.assertRaises(ValueError):
            build('{"fixture":' + json.dumps(record) + ',"fixture":' + json.dumps(record) + '}')
        build(json.dumps({"test-a": record, "test-b": next_record}), False)
        alias_ring = {"fixture-retired": dict(record, valid_from=0, valid_until=1, revoked=True), **ring}
        build(json.dumps(alias_ring))
        for source in [roots, self.app / "steaddeskFleet/java/com/carriez/flutter_hbb/FleetBuild.java"]:
            lines = source.read_text().splitlines()
            self.assertTrue(any("fixture-old" in line and "true" in line for line in lines))
            self.assertTrue(any("fixture-next" in line and "false" in line for line in lines))

    def test_workflow_selects_release_origins_and_provisions_all_build_entries(self):
        workflow = (MODULE.parents[1] / ".github/workflows/build.yml").read_text()
        for name, preview in (("OPS_ORIGIN", "fleet_ops_origin"), ("ARTIFACT_ORIGIN", "fleet_artifact_origin")):
            expression = next(line for line in workflow.splitlines()
                              if line.startswith("  STEADDESK_FLEET_" + name + ": "))
            self.assertIn("github.ref_type == 'tag' && vars.STEADDESK_FLEET_RELEASE_" + name, expression)
            self.assertIn("|| github.ref_type != 'tag' && (inputs." + preview, expression)
        jobs = re.split(r"(?m)^  [a-z][a-z0-9-]*:\s*$", workflow.split("jobs:\n", 1)[1])
        entries = [job for job in jobs if "scripts/apply-patches.sh" in job or "scripts/archive-source.py" in job]
        self.assertEqual(len(entries), 5)
        for entry in entries:
            self.assertLess(entry.index("actions/fleet-build-python"), entry.index("scripts/"))
