#!/usr/bin/env python3
"""Run side-effect-free Java policy checks with a verified org.json dependency."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[2]
jar=Path(sys.argv[1]).resolve()
if hashlib.sha256(jar.read_bytes()).hexdigest()!="3cf6cd6892e32e2b4c1c39e0f52f5248a2f5b37646fdfbb79a66b46b618414ed":
    raise SystemExit("Expected org.json:json:20240303 with pinned SHA-256")
with tempfile.TemporaryDirectory(prefix="fleet-policy-") as tmp:
    subprocess.run(["javac","--release","8","-cp",str(jar),"-d",tmp,str(root/"android-fleet/src/main/java/com/carriez/flutter_hbb/FleetPolicy.java"),str(root/"android-fleet/src/main/java/com/carriez/flutter_hbb/FleetRoot.java"),str(root/"scripts/tests/fleet-policy/FleetPolicyTest.java")],check=True)
    subprocess.run(["java","-cp",tmp+":"+str(jar),"com.carriez.flutter_hbb.FleetPolicyTest"],check=True)
