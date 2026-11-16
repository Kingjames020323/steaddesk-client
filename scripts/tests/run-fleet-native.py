#!/usr/bin/env python3
"""Focused host proof/JNI smoke using pinned hbb_common, not a RustDesk build.

Usage: python3 scripts/tests/run-fleet-native.py PATCHED_PINNED_SOURCE
Requires cargo/rustc on PATH and a JDK. CARGO_HOME/TARGET_DIR can use local caches.
Only fixture identity data and a disposable public release root enter the scratch
build; the Java-generated private release key is never written to disk.
"""
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(sys.argv[1]).resolve()

def run(args, **kw):
    return subprocess.run([str(a) for a in args], check=True, text=True, **kw)

assert subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip() == "fada664df7a294d1d1a9ca3e7cd3637069122f17"
assert subprocess.check_output(["git", "-C", str(SOURCE/"libs/hbb_common"), "rev-parse", "HEAD"], text=True).strip() == "229b904508364c8997aad0fb5af57effac859f60"
patch = (ROOT/"patches/0040a-fleet-native.patch").read_text()
section = patch.split("+++ b/src/steaddesk_fleet_native.rs\n", 1)[1]
module = "".join(line[1:] for line in section.splitlines(True) if line.startswith("+") and not line.startswith("+++"))
manifest = (SOURCE/"Cargo.toml").read_text()
patches = re.search(r"(?ms)^\[patch.crates-io\]\n(.*?)(?=^\[|\Z)", manifest).group(1)
# Root patch section also contains path overrides for full RustDesk. The focused
# probe only needs these registry overrides for hbb_common's dependency graph.
patches = "\n".join(line for line in patches.splitlines() if line.startswith(("tungstenite ", "webrtc ", "webrtc-util ", "webrtc-sctp ")))
with tempfile.TemporaryDirectory(prefix="fleet-native-") as tmp:
    work = Path(tmp)
    (work/"src").mkdir()
    # Compile the exact added build-selector lines, then check the edition/OS
    # matrix independently of the host-only JNI probe below.
    build_hunk = patch.split("diff --git a/src/lib.rs", 1)[0]
    selector_code = "".join(line[1:] for line in build_hunk.splitlines(True)
                            if line.startswith("+") and not line.startswith("+++"))
    (work/"gate.rs").write_text('fn main() { let selector="edition"; let target_os=std::env::var("FIXTURE_OS").unwrap();\n'+selector_code+'}\n')
    run(["rustc", "--edition=2021", work/"gate.rs", "-o", work/"gate"])
    for support, enabled, platform, expect in [
        (False, True, "android", True), (True, True, "android", False),
        (False, False, "android", False), (False, True, "macos", False),
    ]:
        (work/"edition").write_text(str(support).lower())
        (work/"src/steaddesk_fleet.rs").write_text(str(enabled).lower())
        output = subprocess.check_output([str(work/"gate")], cwd=work,
                    env=dict(os.environ, FIXTURE_OS=platform), text=True)
        assert ("cargo:rustc-cfg=steaddesk_fleet_merchant" in output) == expect
    print("Native build selector PASS: merchant Android only, feature default off")
    (work/"classes").mkdir()
    (work/"com/carriez/flutter_hbb").mkdir(parents=True)
    shutil.copyfile(ROOT/"android-fleet/src/main/java/com/carriez/flutter_hbb/FleetNative.java", work/"com/carriez/flutter_hbb/FleetNative.java")
    (work/"NativeFixture.java").write_text('''
import java.nio.file.*;
import java.security.*;
import com.carriez.flutter_hbb.FleetNative;
public class NativeFixture {
  static native void prepare(String path);
  static native void active(boolean value);
  static void require(boolean value) { if(!value) throw new AssertionError(); }
  public static void main(String[] args) throws Exception {
    Path dir=Path.of(args[1]);
    if(args[0].equals("make")) {
      byte[] raw="{\\"release\\":\\"native-fixture\\"}\\n".getBytes(java.nio.charset.StandardCharsets.UTF_8);
      Files.write(dir.resolve("raw"),raw);
      for(String label:new String[]{"old","new","revoked"}) {
        KeyPair pair=KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        byte[] encoded=pair.getPublic().getEncoded();
        Signature signer=Signature.getInstance("Ed25519"); signer.initSign(pair.getPrivate()); signer.update(raw);
        Files.write(dir.resolve(label+".sig"),signer.sign());
        Files.write(dir.resolve(label+".pk"),java.util.Arrays.copyOfRange(encoded,encoded.length-32,encoded.length));
      }
      return;
    }
    System.load(args[2]); require(!FleetNative.initialize("relative")); require(FleetNative.initialize(dir.toString())); require(FleetNative.initialize(dir.toString())); require(!FleetNative.initialize(dir.resolve("other").toString())); prepare(dir.resolve("identity").toString());
    String first=FleetNative.proof("GET","/ops/v1/device/update-identity","{}",0);
    require(first!=null && first.contains("790001001") && first.contains("X-Fleet-Signature"));
    require(!first.equals(FleetNative.proof("GET","/ops/v1/device/update-identity","{}",0)));
    require(FleetNative.proof("POST","/ops/v1/fleet-updates/stop","{}",1)==null);
    require(FleetNative.proof("GET","/ops/v1/device/update-assignment","{}",0)==null);
    require(FleetNative.proof("POST","/ops/v1/device/update-reports","{\\"x\\":1,\\"x\\":1}",1)==null);
    byte[] raw=Files.readAllBytes(dir.resolve("raw"));
    byte[] sig=Files.readAllBytes(dir.resolve("old.sig"));
    require(FleetNative.verifyRelease(raw,sig,"fixture-old"));
    require(FleetNative.verifyRelease(raw,Files.readAllBytes(dir.resolve("new.sig")),"fixture-new"));
    require(!FleetNative.verifyRelease(raw,Files.readAllBytes(dir.resolve("revoked.sig")),"fixture-revoked"));
    require(!FleetNative.verifyRelease(raw,Files.readAllBytes(dir.resolve("revoked.sig")),"fixture-alias"));
    require(!FleetNative.verifyRelease(raw,sig,"fixture-new"));
    require(!FleetNative.verifyRelease(raw,sig,"unknown"));
    raw[0]^=1; require(!FleetNative.verifyRelease(raw,sig,"fixture-old"));
    require(FleetNative.sessionState()==0); active(true); require(FleetNative.sessionState()==2);
    System.out.println("JNI smoke PASS: existing identity, nonce freshness, domains, duplicate rejection, embedded release trust, tamper, session source");
  }
}
''')
    run(["javac", "-d", work/"classes", work/"NativeFixture.java", work/"com/carriez/flutter_hbb/FleetNative.java"])
    run(["java", "-cp", work/"classes", "NativeFixture", "make", work])
    (work/"src/steaddesk_fleet_native.rs").write_text(module)
    # Exercise the actual tagged-build configuration using only ephemeral public fixtures.
    roots = {f"fixture-{label}": {
        "public_key": base64.b64encode((work / (label + ".pk")).read_bytes()).decode(),
        "valid_from": 0, "valid_until": 4102444800, "revoked": label == "revoked",
    } for label in ("old", "new", "revoked")}
    roots["fixture-alias"] = dict(roots["fixture-revoked"], revoked=False)
    (work / "RELEASE_VERSION").write_text("1.5.0-sd.1")
    manifest_path = work / "flutter/android/app/src/steaddeskStaging/AndroidManifest.xml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("<manifest>\n    <application>\n    </application>\n</manifest>\n")
    build_env = {k: v for k, v in os.environ.items() if not k.startswith("STEADDESK_FLEET_")}
    build_env.update(GITHUB_REF_TYPE="tag", STEADDESK_FLEET_UPDATE="1",
                     STEADDESK_FLEET_OPS_ORIGIN="https://fixture.invalid",
                     STEADDESK_FLEET_KEYRING=json.dumps(roots))
    run([sys.executable, ROOT/"scripts/configure-fleet.py", work, "merchant"], env=build_env)
    (work/"src/lib.rs").write_text('''
#![allow(unexpected_cfgs)]
pub mod server { pub static AUTHED_CONNS: std::sync::Mutex<Vec<i32>> = std::sync::Mutex::new(Vec::new()); }
#[cfg(steaddesk_fleet_merchant)] mod steaddesk_fleet_native;
#[no_mangle] pub extern "system" fn Java_NativeFixture_prepare(mut env:jni::JNIEnv,_:jni::objects::JClass,path:jni::objects::JString) {
  let path:String=env.get_string(&path).unwrap().into();
  *hbb_common::config::APP_NAME.write().unwrap()=path.clone();
  assert_eq!(hbb_common::config::Config::file(),std::path::PathBuf::from(path).with_extension("toml"));
  hbb_common::config::Config::set_id("790001001"); hbb_common::config::Config::get_key_pair();
}
#[no_mangle] pub extern "system" fn Java_NativeFixture_active(_:jni::JNIEnv,_:jni::objects::JClass,v:jni::sys::jboolean) {
  let mut guard=server::AUTHED_CONNS.lock().unwrap(); guard.clear(); if v!=0 { guard.push(1); }
}
''')
    (work/"Cargo.toml").write_text(f'''[package]
name="fleet-native-probe"
version="0.1.0"
edition="2021"
[lib]
crate-type=["cdylib","rlib"]
[dependencies]
hbb_common={{path={json.dumps(str(SOURCE/"libs/hbb_common"))}}}
serde_json="=1.0.118"
jni="=0.21.1"
[patch.crates-io]
{patches}
''')
    # Reuse pinned resolution, without building the full client.
    shutil.copyfile(SOURCE/"Cargo.lock", work/"Cargo.lock")
    env = os.environ.copy()
    env["RUSTFLAGS"] = "--cfg=steaddesk_fleet_merchant"
    run(["cargo", "test", "--offline", "--manifest-path", work/"Cargo.toml", "--lib"], env=env)
    run(["cargo", "build", "--offline", "--manifest-path", work/"Cargo.toml", "--lib"], env=env)
    target = Path(env.get("CARGO_TARGET_DIR", str(work/"target"))).resolve()
    suffix = ".dylib" if sys.platform == "darwin" else ".so"
    lib = target/"debug"/("libfleet_native_probe"+suffix)
    shutil.copyfile(lib, work/("librustdesk"+suffix))
    run(["java", "-Djava.library.path="+str(work), "-cp", work/"classes", "NativeFixture", "smoke", work, work/("librustdesk"+suffix)])
    env["RUSTFLAGS"] = ""
    run(["cargo", "build", "--offline", "--manifest-path", work/"Cargo.toml", "--lib"], env=env)
    symbols = subprocess.check_output(["nm", "-g", str(lib)], text=True)
    assert "Java_com_carriez_flutter_1hbb_FleetNative_" not in symbols
    print("Feature-off native symbols absent PASS; no Android or real-session acceptance claimed")
