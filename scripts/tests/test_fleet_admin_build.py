"""Fleet admin is default-off and excluded from the merchant import graph."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

class FleetAdminBuildTest(unittest.TestCase):
    def test_support_merchant_and_disabled_selectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree=Path(tmp)
            for path in ('libs/hbb_common/src','flutter/windows/runner','flutter/android/app/src/main'):
                (tree/path).mkdir(parents=True)
            (tree/'RELEASE_VERSION').write_text('1.5.0-sd.2')
            (tree/'flutter/android/app/src/main/AndroidManifest.xml').write_text('<manifest>\n    <queries></queries>\n    <application>\n        <receiver><intent-filter><action android:name="android.intent.action.BOOT_COMPLETED" /></intent-filter></receiver>\n    </application>\n</manifest>')
            for edition,flag,enabled in [('support','',False),('support','true',True),('merchant','true',False),('support','false',False),('merchant','',False),('support','1',True)]:
                with self.subTest(edition=edition,flag=flag):
                    env={**os.environ,'STEADDESK_FLEET_ADMIN':flag,'STEADDESK_FLEET_UPDATE':'false'}
                    subprocess.run(['bash',str(ROOT/'scripts/configure-edition.sh'),str(tree),edition],env=env,check=True,capture_output=True,text=True)
                    lib=tree/'flutter/lib/steaddesk'
                    self.assertIn('const fleetAdminEnabled = '+str(enabled).lower()+';',(lib/'merchant_build.dart').read_text())
                    self.assertEqual((lib/'fleet_admin_api.dart').read_text(),"export 'fleet/"+('fleet_admin_host' if enabled else 'fleet_admin_off')+".dart';\n")
    def test_invalid_flag_stops_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree=Path(tmp)
            for path in ('libs/hbb_common/src','flutter/windows/runner'):(tree/path).mkdir(parents=True)
            result=subprocess.run(['bash',str(ROOT/'scripts/configure-edition.sh'),str(tree),'support'],env={**os.environ,'STEADDESK_FLEET_ADMIN':'maybe'},capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('STEADDESK_FLEET_ADMIN',result.stderr)
