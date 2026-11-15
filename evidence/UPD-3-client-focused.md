# UPD-3 support fleet administration client

This is an opt-in support-edition feature. `STEADDESK_FLEET_ADMIN` defaults off;
`configure-edition.sh` emits `fleetAdminEnabled` and selects the no-op host for the
merchant edition and disabled support builds. The merchant import graph does not
reference the fleet HTTP client or management widgets. Enabling the flag supplies
no account authority: only a fresh authenticated `capabilities.publish=true`
response exposes the header or panel. It does not depend on a cached admin flag.

The normal support homepage mounts a full-width red emergency-stop header above
its existing home header. Stop requires one confirmation. Global resume requires
an initial confirmation, a nonempty bounded reason, and a final confirmation; it
is hidden without explicit current resume authority. Release pause, resume and
advance collect reasons. Progression buttons use the server's `can_activate`
boolean and show its gate reason; this client never sends `approve_small_sample`.
The panel displays ring/batch/state, failure/healthy/observing-or-waiting/deferred
counts, global generation/operator/time, and at most 20 management audit rows.

`FleetAdminHttp` is pure Dart (`dart:io`, no Flutter imports), uses system TLS trust
by default, accepts HTTPS origins only, disables redirects and sends the current
account's Bearer token. It binds account/token/origin across a fresh capability and
eligibility GET, the mutation POST and its subsequent refresh. The production host
also fixes the identity at controller creation, so switching accounts, tokens or
origins while a confirmation dialog is open cannot migrate the confirmation to a
new identity. Late results are discarded. No credential or management-data cache is
written to disk. Poll reads are single-flight and invalidated by action epochs so
an older poll cannot overwrite a newer stop or permission state.

The additive server contract is `GET /ops/v1/fleet-updates` with
`capabilities.publish/stop/resume`, `safety`, authoritative batch eligibility and
management-only audit. POST actions are `stop`, `resume`, `pause-release`,
`resume-release` and `activate`. Nonpublisher responses may omit every sensitive
aggregate field and parse as an empty denied dashboard. Malformed publisher safety
booleans are rejected rather than displayed as a legitimate stopped state.

## Focused validation

- Distribution suite: `python3 -B -m unittest discover -s scripts/tests -v`:
  **25 tests passed**, including enabled support, disabled support and merchant
  selector transitions, invalid flag rejection and existing packaging tests.
- Targeted Flutter suite: `flutter test --no-pub test/steaddesk/fleet_admin_test.dart`:
  **16 tests passed** using the cached pinned Flutter SDK and package metadata.
  Coverage includes role visibility, one-confirm stop, three-stage global resume,
  release action reasons, authoritative disabled progression, aggregate/audit
  display, account switch during confirmation, token/origin binding, clearing
  revoked views, retired responses and the old-poll-after-stop race.
- `dart analyze` on the new HTTP client, host, widgets and tests: **no issues**.
- `0041-fleet-admin.patch` checks cleanly against the full previously applied queue;
  `git diff --check` passes. Existing patch files were not regenerated.
- The actual local HTTPS exercise initially caught Dart's default chunked POST
  framing, which the service correctly rejects. The client now sets Content-Length
  to the encoded UTF-8 byte count. The independent real-service exercise subsequently
  accepted the real Dart request, including Unicode reasons. Its receipt is separate
  from these widget tests and does not imply a deployed service.

## Widget render

`UPD-3-widget.png` is a visually inspected **synthetic Flutter widget-test render**
at 1200×900. It uses public synthetic IDs/counts, an opaque Material background and
locally loaded CJK/Material icon fonts. The paused release correctly has its pause
button disabled; the small-sample gate disables progression while resume remains
available. Text, counts, audit and icons are readable without clipping or overflow.
It is not a Windows application screenshot, production data or device acceptance.

For a local render, set `FLEET_ADMIN_FONT` and `FLEET_ADMIN_ICONS` to readable local
font files and `FLEET_ADMIN_RENDER` to an output PNG before the targeted test.

## Pure Dart probe interface

Import `flutter/lib/steaddesk/fleet/fleet_admin_client.dart` from the patched source.
Create `FleetAdminHttp(identity: currentIdentity)` where `currentIdentity` resolves
a `FleetAdminIdentity(origin: ..., account: ..., token: ...)` on every call. Use
`boundIdentity` for an interactive confirmation scope. Production uses default TLS
trust; a disposable loopback fixture may explicitly provide a SecurityContext with
its own test CA, without disabling certificate validation.

`fetch()` returns `FleetDashboard`. `act('stop', generation: ..., reason: ...)`
and `act('resume', ...)` compare the displayed generation to a fresh server result.
Release actions take `release` and `reason`. `close()` retires the HTTP transport.
No private fixture sources, CA/identity secrets, production origins or credentials
are included in this public change. Full application CI, real Windows interaction
and production deployment remain separate verification stages.
