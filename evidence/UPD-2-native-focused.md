# UPD-2 native bridge focused checks

2026-11-14 local host evidence; no publication, CI dispatch, full RustDesk build,
Android N→N+1 installation, physical device, or real remote-session acceptance.

Pinned source was RustDesk `fada664df7a294d1d1a9ca3e7cd3637069122f17` and
hbb_common `229b904508364c8997aad0fb5af57effac859f60`, with the preceding patch
queue applied. `git apply --check` accepted `0040a-fleet-native.patch` there.
The host runner verifies these two source identities before compiling.

Run with Cargo, rustc and a JDK on PATH and the dependency cache available:

```sh
python3 scripts/tests/run-fleet-native.py "$PATCHED_PINNED_SOURCE"
```

Observed: all four Rust tests passed. They cover restricted route/method/version
and canonical-body acceptance, exact protocol bytes and detached-signature
binding, raw release bytes/root/time/signature rejection, and existing HELP-2
identity plus fresh nonces. Identity tests use only a new isolated temporary
configuration; the updater does not create replacement identities.

Observed: the real `FleetNative.java` declarations called the compiled native
module in a local JVM successfully. Tests accepted a detached Ed25519 manifest
under the compiled fixture public root and rejected altered bytes and another
supplied root; accepted fresh identity proofs and rejected admin routes, version
zero on assignment, and duplicate keys; checked initialization with the same
absolute configuration directory, rejection of relative/different directories,
and idle/active session values. The release fixture private key exists only in
Java memory. Its public root, manifest and detached signature are temporary.

Observed: compilation of the actual added build-selector code accepted only
merchant + enabled + Android, rejecting support, feature off, and macOS cases.
A feature-off host library exported no `FleetNative` JNI entry points.

The JVM session check uses a host fixture for `AUTHED_CONNS`; the product JNI
reads the existing Rust server's authorized incoming connection collection.
This confirms JNI wiring and interpretation, not Android session behavior.
The focused host build uses the pinned hbb_common directly and a small server
collection fixture; it does not compile the entire RustDesk Android library.
Android ABI linking, PackageInstaller and boot/update receipts remain separate
integration gates.

Regression surface: only build.rs gains a separate compile selector, and
src/lib.rs gains an Android/merchant/feature-gated module. Existing service,
mediator, HELP-2 signing and configuration paths are not rerouted. The new JNI
initializer locates an existing application-private directory without starting
a service or generating keys. Release verification compares the supplied key
to the build-embedded public root independently of Java before raw-byte
Ed25519 verification. Device signing accepts only identity discovery and the
four fixed update operations; no caller-controlled device ID, clock, nonce,
private key or signing domain is accepted or returned.
