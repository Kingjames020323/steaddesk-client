"""Overlay the Android S6 entry point on a disposable, already-patched merchant build tree."""
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
assets = Path(__file__).resolve().parent
staging = tree / "flutter/android/app/src/steaddeskStaging"
manifest = staging / "AndroidManifest.xml"
android = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", android)
ET.register_namespace("tools", "http://schemas.android.com/tools")
a = "{" + android + "}"
xml = ET.parse(manifest)
root = xml.getroot()
app = root.find("application")
service, = app.findall(f"service[@{a}name='.MainService']")
if service.get(a+"exported") != "false":
    raise ValueError("unexpected baseline MainService exposure")
service.set(a+"exported", "true")
service.set(a+"permission", "com.steaddesk.agent.s6.START_MERCHANT")
permission = "com.steaddesk.remote.s6.START_AGENT"
root.insert(0, ET.Element("permission", {a+"name": permission, a+"protectionLevel": "signature"}))
root.insert(1, ET.Element("uses-permission", {a+"name": permission}))
ET.SubElement(root.find("queries"), "package", {a+"name": "com.steaddesk.agent"})
ET.SubElement(app, "provider", {a+"name": "com.steaddesk.remote.s6.SelfHealProvider",
                               a+"authorities": "com.steaddesk.remote.s6", a+"exported": "true",
                               a+"grantUriPermissions": "false"})
ET.indent(xml, space="    ")
xml.write(manifest, encoding="utf-8", xml_declaration=True)
shutil.copytree(assets / "java", staging / "java", dirs_exist_ok=True)
