# UPD-2 Android focused implementation checks

Local checks on the candidate source, without a full RustDesk build or deployment:

- Distribution Python suite: `python3 -B -m unittest discover -s scripts/tests -v`:
  22 tests passed. Includes five new fleet selector tests and existing merchant /
  support / merchant reconfiguration regression.
- Pure Java policy runner: `python3 scripts/tests/run-fleet-policy.py` with the
  verified org.json 20240303 JAR: 25 checks passed. Covers strict canonical JSON,
  duplicate/permissive/invalid JSON, crossing midnight, both DST transitions,
  unknown time zones, invalid bounds, pause, force-stop, active/unknown session,
  local business-day and rolling-24h budget, clock rollback and active transaction.
- All production fleet Java files compile with `javac --release 8`, Android SDK 36
  API JAR and apksig 8.1.4. Small compile-only stubs represent existing app symbols
  (MainService, MerchantRecovery, Flutter PathUtils, generated resources/config).
  This proves Java type compatibility of this component, not a full application
  link, actual Flutter lifecycle or device health.
- `0040b-fleet-android-entry.patch` applies cleanly to the pinned complete existing
  distribution queue. `git diff --check` passes.

The dependency digests used for these local checks:

| Artifact | SHA-256 |
| --- | --- |
| org.json:json:20240303 | `3cf6cd6892e32e2b4c1c39e0f52f5248a2f5b37646fdfbb79a66b46b618414ed` |
| com.android.tools.build:apksig:8.1.4 | `468ee1852fa12461c6629608fe47be70e50f60be7c4744bb7f62ca48e85c0a6c` |
| google-java-format 1.24.0 all-deps | `812f805f58112460edf01bf202a8e61d0fd1f35c0d4fabd54220640776ec57a1` |

Java production sources were formatted with the pinned formatter after
implementation and review fixes. No formatter dependency is added to the shipped app.

Native proof / root / selector / JNI evidence is recorded separately in
`UPD-2-native-focused.md`. The emulator fixture owns its separate real HTTPS and
PackageInstaller evidence and records source hashes. No physical firmware approval,
production authorization, four-hour observation acceptance, or full application
build is inferred from these focused checks.

The production receiver was reviewed for Android execution limits and changed to
short durable capture plus JobScheduler scheduling only. Callback queue snapshots
and acknowledgments hold no locks across network or installer work. The full set
of production Java sources, including this inbox and receiver, passes the focused
SDK36/apksig compile; receiver/job lifecycle on a device remains outside the runtime
fixture coverage. Runtime and policy source hashes are unchanged by this adapter fix.
