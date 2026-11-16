#!/usr/bin/env python3
"""Compile unchanged candidate Runtime+Policy into two disposable signed APKs.
No device writes or network access. All generated files stay in external scratch.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def run(*args):
    subprocess.run([str(x) for x in args], check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sdk", required=True, type=Path)
    p.add_argument("--build-tools", default="35.0.0")
    p.add_argument("--platform", default="34")
    p.add_argument("--apksig", required=True, type=Path)
    p.add_argument("--eddsa", required=True, type=Path)
    p.add_argument("--scratch", required=True, type=Path)
    p.add_argument("--config", required=True, type=Path)
    a = p.parse_args()
    fixture = Path(__file__).resolve().parent
    repo = fixture.parents[2]
    scratch = a.scratch.resolve()
    if scratch == repo or repo in scratch.parents:
        p.error("scratch must be outside repository")
    scratch.mkdir(parents=True, exist_ok=True)
    if hashlib.sha256(a.apksig.read_bytes()).hexdigest() != "468ee1852fa12461c6629608fe47be70e50f60be7c4744bb7f62ca48e85c0a6c":
        p.error("apksig 8.1.4 digest mismatch")
    if hashlib.sha256(a.eddsa.read_bytes()).hexdigest() != "4dda1120db856640dbec04140ed23242215a075fe127bdefa0dcfa29fb31267d":
        p.error("EdDSA 0.3.0 digest mismatch")
    config = json.loads(a.config.read_text())
    if not config["key_id"].startswith("test-") or not config["origin"].startswith("https://"):
        p.error("fixture requires test release identity and HTTPS")
    tools = a.sdk / "build-tools" / a.build_tools
    android = a.sdk / "platforms" / ("android-" + a.platform) / "android.jar"
    generated = scratch / "generated"
    generated.mkdir(exist_ok=True)
    fields = {"OPS_ORIGIN": config["origin"], "ARTIFACT_ORIGIN": config["origin"],
              "SILENT_PROFILE": config["silent_profile"]}
    java = "package com.carriez.flutter_hbb; final class FleetBuild {\n"
    java += "\n".join("static final String " + k + "=" + json.dumps(v) + ";" for k,v in fields.items())
    java += ("\nstatic final FleetRoot[] ROOTS = {new FleetRoot(" + json.dumps(config["key_id"]) + ", " +
             json.dumps(config["public_key"]) + ", 0L, 4102444800L, false)};\n}\n")
    (generated / "FleetBuild.java").write_text(java)
    (generated / "FixtureSecrets.java").write_text(
        "package com.carriez.flutter_hbb; final class FixtureSecrets {\n" +
        "static final String DEVICE=" + json.dumps(config["device"]) + ";\n" +
        "static final String DEVICE_PKCS8=" + json.dumps(config["device_pkcs8"]) + ";\n}\n")
    res = scratch / "res"
    (res / "raw").mkdir(parents=True,exist_ok=True)
    (res / "xml").mkdir(exist_ok=True)
    (res / "raw" / "fixture_ca.pem").write_bytes((a.config.parent / "tls.pem").read_bytes())
    (res / "xml" / "network_security_config.xml").write_text(
        '<network-security-config><base-config cleartextTrafficPermitted="false"><trust-anchors>'
        '<certificates src="@raw/fixture_ca" /></trust-anchors></base-config></network-security-config>')
    run(tools / "aapt2", "compile", "--dir", res, "-o", scratch / "resources.zip")
    classes = scratch / "classes"
    classes.mkdir(exist_ok=True)
    candidate = repo / "android-fleet/src/main/java/com/carriez/flutter_hbb"
    snapshot = scratch / "candidate-source"
    snapshot.mkdir(exist_ok=True)
    for name in ("FleetRuntime.java", "FleetPolicy.java", "FleetRoot.java", "FleetArchive.java"):
        (snapshot / name).write_bytes((candidate / name).read_bytes())
    sources = [*snapshot.glob("*.java"), *fixture.glob("*.java"), *generated.glob("*.java")]
    run("javac", "--release", "8", "-classpath", str(android) + ":" + str(a.apksig) + ":" + str(a.eddsa), "-d", classes, *sources)
    run("jar", "cf", scratch / "classes.jar", "-C", classes, ".")
    dex = scratch / "dex"
    dex.mkdir(exist_ok=True)
    run(tools / "d8", "--lib", android, "--min-api", "31", "--output", dex, scratch / "classes.jar", a.apksig, a.eddsa)
    key = scratch / "fixture.p12"
    if not key.exists():
        run("keytool", "-genkeypair", "-keystore", key, "-storepass", "android", "-keypass", "android", "-alias", "test", "-dname", "CN=UPD2 Disposable Fixture", "-keyalg", "RSA", "-validity", "1", "-noprompt")
    ns = "{http://schemas.android.com/apk/res/android}"
    for name,version in (("N",69),("N-plus-1",70)):
        manifest = ET.parse(fixture / "AndroidManifest.xml")
        manifest.getroot().set(ns + "versionCode", str(version))
        manifest.getroot().set(ns + "versionName", "UPD2-fixture-" + str(version))
        path = scratch / (name + "-manifest.xml")
        manifest.write(path,encoding="utf-8")
        unsigned = scratch / (name + "-unsigned.apk")
        run(tools / "aapt2", "link", "-I", android, "--manifest", path, "-o", unsigned, scratch / "resources.zip")
        with zipfile.ZipFile(unsigned,"a") as apk:
            for d in dex.glob("classes*.dex"):
                apk.write(d,d.name)
        aligned = scratch / (name + "-aligned.apk")
        run(tools / "zipalign", "-f", "4", unsigned, aligned)
        run(tools / "apksigner", "sign", "--ks", key, "--ks-pass", "pass:android", "--out", scratch / (name + ".apk"), aligned)
    certs = subprocess.check_output([str(tools / "apksigner"),"verify","--print-certs",str(scratch / "N-plus-1.apk")],text=True)
    signer = next(x.split(": ",1)[1] for x in certs.splitlines() if "certificate SHA-256 digest:" in x)
    (scratch / "publish.json").write_text(json.dumps({"signer_cert_sha256":signer}))
    metadata = {"signer_cert_sha256":signer,"source_sha256":{s.name:hashlib.sha256(s.read_bytes()).hexdigest() for s in sources if s.parent == snapshot},
                "apk_sha256":{n:hashlib.sha256((scratch / (n+".apk")).read_bytes()).hexdigest() for n in ("N","N-plus-1")}}
    (scratch / "build-metadata.json").write_text(json.dumps(metadata,sort_keys=True,indent=2))
    print(json.dumps(metadata,sort_keys=True))


if __name__ == "__main__":
    main()
