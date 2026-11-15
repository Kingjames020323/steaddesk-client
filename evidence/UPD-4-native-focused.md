# UPD-4 merchant Windows controller focused evidence

Local verification on the candidate patch; no full RustDesk build, native Windows
execution, live merchant installation, production deployment, physical acceptance
or automatic rollback result is inferred.

The controller links only for the explicit Windows merchant feature and native
selector. Its lifecycle hook is in the existing `start_server(is_server=true)`
path before the rendezvous mediator. This is the existing SCM-owned `--server`
child, where the HELP identity and live incoming session collection reside; the
SCM wrapper's separate, empty session collection cannot authorize installation.
The native platform gate independently proves the installed process path and
SCM parent/creation identity and the existing companion service state.

The worker uses the existing Config-held Ed25519 identity and the fixed five
fleet message domains. It discovers the bound registration revision over HTTPS,
uses fresh native nonce/time and canonical request bytes, and exports no private
key or arbitrary signing entry. TLS uses system trust, fixed configured origins,
no proxy/redirect handling, and bounded requests. Signed release bytes are
verified against the compiled test-only root before interpreting artifact paths.
The clock combines authenticated HTTPS Date with elapsed time and requires the
native signing clock to agree within 30 seconds.

IANA windows reject ambiguous/nonexistent local times and transitions across the
window. Preparation and the final OS boundary check J23, actual local sessions,
current installed build/identity, business date, rolling 24-hour budget, assignment
expiry, fresh safety nonce/generation/purpose/expiry, and one-use server grant.
After the submitted state is durably written, the worker checks the entire
current service build/PID/creation/hash snapshot, volatile gates, time, lease and
reserved business date again immediately before launch. A persisted or ambiguous
attempt is reconciled without repeating the installer.

An EXE wrapper exit of 0 is launch acceptance, not health: the pinned portable
launcher spawns its child and returns. Its first receipt has installer_code=0
without service/identity heartbeat evidence. Health later requires the actual
replacement service process and the exact inner payload digest bound by the
trusted outer signature. Code 3010 remains pending_reboot until a changed native
kernel boot identity and that same readback are proven. A missing/unknown installer
result never becomes an invented zero. Failed/unknown service, time, gate or
recovery evidence holds installation. Native wait timeout retains the installer
lease/deny-write-delete handles and never launches again.

Retained evidence is the prior observed service build/hash/PID/creation, the
signer-bound target release metadata, outer artifact hash, signed payload hash,
OS tracking token and receipt state. The last candidate remains until another
preparation. The updater has no trusted copy of the pre-existing full installer
before its first update; this is not a C4 rollback archive. No downgrade, uninstall,
Agent provisioning, password reset or automatic rollback path is added. MSI and
unapproved/unknown profiles hold.

Observed local results:

- Four intrinsic Rust tests passed: strict duplicate/fractional JSON/domain
  rejection; canonical signing bytes; detached release/root/tamper rejection;
  DST/cross-midnight windows; existing isolated HELP identity and nonce freshness.
- Independent portable controller fixture initially passed 14 tests, including
  those four and real candidate state-machine cases for 0, 3010, failure,
  ambiguous launch/reconciliation, local gates, versions and verifier rejection.
  The fixture runner and any subsequent expanded final result are recorded in
  `scripts/tests/windows-fleet/` and its own evidence.
- The actual Windows Rust host and controller cross-checked successfully for
  `x86_64-pc-windows-gnu` with pinned hbb_common. This used a real MinGW-built
  archive from the bundled libsodium source; it did not substitute a fake crypto
  library. The first default libsodium-sys cross build rejected the Rust target
  triple, so the dependency was built with its proper MinGW autoconf host triple.
- Full existing source Cargo metadata accepted the Windows feature with
  `--locked --offline`. The lockfile preserves upstream package order, adding
  only pinned chrono-tz 0.10.4, phf 0.12.1, phf_shared 0.12.1 and the dependency
  reference. Their declared minimum Rust versions are 1.65/1.61/1.61.
- Patch application/reversal checks passed on RustDesk
  `fada664df7a294d1d1a9ca3e7cd3637069122f17` plus the preceding queue and
  hbb_common `229b904508364c8997aad0fb5af57effac859f60`.

Reproduce the concrete host type check after applying/configuring that source:

```sh
python3 scripts/tests/run-windows-fleet-native.py --source-root "$PATCHED_SOURCE"
```

For a configured cross toolchain add `--target x86_64-pc-windows-gnu`; ordinary
native Windows uses its own installed toolchain. This focused probe compiles the
actual host with compile-only existing-app API peers. It does not link or run a
full product/service. Windows Authenticode, held handles, signed PE test fixtures
and actual exit-code execution belong to the separately owned platform fixture.

Regression surface is limited to two cfg-gated module/lifecycle hooks and an
optional Windows-only dependency/feature. Existing service creation, IPC,
connection/session handling, configuration identity, Android updates, user
startup and support-edition paths are not rewritten.
