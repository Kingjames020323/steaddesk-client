# Merchant fleet updates (preview, default off)

The normal merchant application starts this component through `FleetEntry` after
native initialization, on merchant app launch, on boot/package replacement, through
the existing authenticated merchant recovery wake, and through a persisted six-hour
JobScheduler task. Wake only requests evaluation. It grants no installation rights.
The support and disabled merchant source selections contain only a no-op entry.
Neither selection includes the updater's classes, manifest entries or APK verifier.

Enable only for an explicitly configured preview build:

```sh
STEADDESK_EDITION=merchant \
STEADDESK_FLEET_UPDATE=true \
STEADDESK_FLEET_OPS_ORIGIN=https://preview-ops.example.invalid \
STEADDESK_FLEET_ARTIFACT_ORIGIN=https://preview-artifacts.example.invalid \
bash scripts/apply-patches.sh /path/to/pinned/source
```

Those `.invalid` origins are documentation placeholders. A build requires an HTTPS
origin, rejects credentials, queries and URL paths, and never follows redirects.
The artifact origin defaults to the explicitly configured ops origin. The preview
root `test-upd2-v1` is compiled into Java and the merchant native verifier; its random
private counterpart was discarded. To build a usable disposable test package,
supply `STEADDESK_FLEET_TEST_KEY_ID` (must start `test-`) and
`STEADDESK_FLEET_TEST_PUBLIC_KEY` (canonical base64 Ed25519 public key) at trusted
build time. There is no downloaded keyring, runtime key replacement, device-key
export, or bypass verifier. Enabled tagged builds are rejected. Production release
roots require a separate reviewed change.

A nonempty `STEADDESK_FLEET_SILENT_PROFILE` is the lowercase SHA-256 of the approved
firmware's UTF-8 `Build.FINGERPRINT`, and must equal both the current device's value
and its authenticated enrollment profile. An empty or mismatched value, and all
Android 11 devices, require a merchant offer and explicit acceptance. This compiled
fingerprint alone does not enroll or approve firmware. The backend still authorizes
the particular installation. A system request for confirmation is reported as
`pending_user_action` and exposes an immutable user-tapped notification to the
resolved system installer. It is never counted as success or auto-accepted.

Every operation uses a fresh HELP-2 Config identity proof. Key-version discovery
uses its own allowlisted signed identity route with version zero; subsequent
requests use the currently trusted ledger version. The authenticated assignment
must include `ring`, `silent_profile` and
`window={zone,start_min,end_min,business_day}`. Missing scheduling metadata stops
the device. This is the additive companion contract required alongside the original
assignment protocol.

The device verifies the exact manifest bytes before parsing fields. The manifest
must identify the fixed merchant Android package, valid build-time release root,
strictly greater installed version and persisted release sequence. Private-file
downloads have exact byte and SHA-256 bounds; apksig 8.1.4 verifies the complete APK
signature, and the actual certificate, package, version and minimum OS are checked.
The current installed signer must match. No package manager metadata-only signature
check is used as a substitute for full APK verification.

Both local time and the server gate must allow installation. The production clock
requires Android automatic time, a server-authenticated HTTPS Date sample bounded
by monotonic elapsed time, and at most 30 seconds of wall-clock discrepancy. Missing
time, any DST transition within the configured store window, session state unknown
or active, merchant pause, relevant application force-stop, same business day or
rolling 24-hour usage all stop installation. Immediately before the OS boundary,
the device obtains a new nonce-bound online safety permit and a new server commit
with `install_authorized=true`. Cached permits, identical commit retries, push
messages and reconciliation responses never authorize installation.

`noBackupFilesDir/fleet-update` holds an atomic state file, a process/OS file lock,
private candidate APK, an ordered durable report outbox and fixed-code JSONL
events. Identity secrets, authentication headers and permits are not logged or
persisted by the updater. The local transaction and daily budget are persisted
before submitting the attempt. An ambiguous commit response or process death never
replays `PackageInstaller.commit`. Recovery first queries the saved OS session,
then reconciles its authenticated server transaction and installed identity.
Unknown sessions require manual handling. Confirmed server terminal records retire
only matching receipt backlog; audit history and cooldown survive. Confirmed failed
transactions retire locally only after the OS session no longer exists, allowing a
separately authorized newer repair after server unfreezing and cooldown.

OS success starts observation. It does not mark the device healthy. Recovery checks
the installed APK digest, signer, target version and actual merchant service plus
known native session state. Health uses one timestamp sample for `observed_at` and
`heartbeat_at`. A persisted job targets the server's four-hour deadline minus four
minutes, then checks at bounded short intervals in the final window. Job scheduling
or service unavailability cannot produce false health; the server freezes missing
observations. Merchant pause preserves the transaction. No uninstall, downgrade,
data clearing, shell/adb execution, service restart, or compensation install exists
in this component.

Focused checks, without building the full RustDesk app:

```sh
python3 -B -m unittest discover -s scripts/tests -v
python3 scripts/tests/run-fleet-policy.py /external/org-json-20240303.jar
python3 scripts/tests/run-fleet-native.py /path/to/patched/pinned/source
```

The policy runner verifies the pinned org.json dependency hash before compiling.
The native runner uses the pinned common source and real Config identity. Emulator
fixture instructions and their explicit Java/native/host boundaries are in
`../scripts/tests/fleet/README.md`; emulator evidence does not replace the two
merchant firmware and production-network acceptance gates.
