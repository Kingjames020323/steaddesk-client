# UPD-2 isolated Android platform fixture

This fixture compiles the candidate `FleetRuntime.java`, `FleetPolicy.java` and `FleetArchive.java`
unchanged into a small Android application. A separate local test driver provides
a fresh, disposable AOSP emulator and authenticated HTTPS service implementing the
published fleet protocol. The fixture performs the actual self-update through the
candidate runtime and Android PackageInstaller.

The fixture Host samples its authenticated test server TLS Date and advances it
with monotonic elapsed time, as the production integration does. The request
proof uses fresh Ed25519 signatures and nonces.

The fixture's Host replaces the full application's Rust JNI identity and live
session/service integration with explicit test inputs and real Java Ed25519
cryptography. `healthy()` means only fixture health. The activity/receiver and
`FleetUpdater` adapters are fixture code; the production scheduler, receiver,
notification, Rust JNI signing, remote service, remote-frame recovery, physical
merchant devices and production deployment are outside this fixture's coverage.

Use build-tools 35.0.0, platform 34, JDK 17 or later, Python 3 and pinned
`com.android.tools.build:apksig:8.1.4` and test-only
`net.i2p.crypto:eddsa:0.3.0` (API 34 AOSP lacks Java Ed25519 KeyFactory). The dependency SHA-256 used in the observed
run was `468ee1852fa12461c6629608fe47be70e50f60be7c4744bb7f62ca48e85c0a6c`;
verify the downloaded dependency before use. EdDSA 0.3.0 SHA-256 is
`4dda1120db856640dbec04140ed23242215a075fe127bdefa0dcfa29fb31267d`.
The builder checks both pinned dependency digests.

The local driver places `tls.pem` and a `config.json` in an external scratch
directory. The JSON contains `origin` (HTTPS), `key_id` (`test-` prefix),
`public_key` (32-byte release key, Base64), `device` (synthetic test ID), and
`device_pkcs8` (Base64 PKCS#8 Ed25519 disposable test identity), and
`silent_profile` (SHA-256 of the disposable emulator firmware fingerprint). No runtime trust
root import occurs: the fixture compiles these inputs as its own test build.
Never commit the config, keys, generated Java, APKs, databases or AVD data.

```sh
python3 scripts/tests/fleet/build-fixture.py \
  --sdk "$ANDROID_HOME" --apksig /external/scratch/apksig.jar \
  --eddsa /external/scratch/eddsa.jar \
  --scratch /external/scratch/run --config /external/scratch/run/config.json
```

The builder generates N (versionCode 69) and N+1 (70), signed with one ephemeral
APK signing certificate. It records the exact candidate source hashes, APK
hashes and certificate fingerprint in `build-metadata.json`. It performs no
network or device operations. The local driver serves N+1 using a signed manifest
whose size, SHA-256, package, version and signer match the generated APK.

ADB is permitted only for fresh emulator setup, initial N deployment, local
transport routing, harness launch and read-only evidence. N+1 must be downloaded
by the app over HTTPS and installed by the candidate PackageInstaller path. Do
not use `adb install -r`, `pm install`, or shell package sessions for the update.
Never point a local driver at a physical device or an existing AVD.

Wait for the fresh emulator to complete boot and reach uptime greater than 45
seconds before launching the fixture. AOSP API 34 silent-update throttling can
require confirmation even for the first update during the first 30 seconds of
uptime; the driver must wait normally and must not disable the system policy.

After a successful update, launch a new activity with `probe_duplicates=true`
to inject two synthetic late pending-user-action callbacks and one duplicate
success into the candidate runtime. The probe requires an existing observing
transaction and asserts its stage and report sequence remain unchanged. This is
a labeled synthetic callback test; actual install evidence comes from the OS
callback and installed package identity.

For negative intake tests, the activity also accepts `probe_case` with one of
`equal`, `lower`, `manifest`, `signature`, `apk_hash`, `apk_signature`, or
`emergency`. Each case uses an isolated private transaction directory and the
same unchanged candidate runtime. The external test driver supplies the matching
signed synthetic envelope or stop state. The activity expects a candidate
rejection; it logs an error if intake unexpectedly proceeds. Check the app's
installed version, installer session history and backend attempts as independent
evidence that no installation was submitted. `apk_signature` must use a corrupted
APK whose changed size/hash are covered by a valid test release signature, so it
reaches the real Android APK signature verifier.

The fixture calls the unchanged `FleetArchive.preserve()` before querying and
`requireCurrent()` before sending attempt proof, matching the production host
seam. Check the signed APK baseline and identity receipt in app-private storage;
an initial/untracked build must explicitly record its prior signed manifest as
unavailable, and it must never authorize automatic rollback.
