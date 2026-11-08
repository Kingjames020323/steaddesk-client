# Upstream history

| Date | Component | Pin |
| --- | --- | --- |
| 2026-11-07 | RustDesk 1.5.0 | fada664df7a294d1d1a9ca3e7cd3637069122f17 |
| 2026-11-07 | hbb_common from that tree | 229b904508364c8997aad0fb5af57effac859f60 |

The Flutter title reads the native application name. Android retains its upstream Java namespace for JNI and changes the installable application ID. The app's About views link to the distribution source. [Flutter app title](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/flutter/lib/main.dart#L498-L500)

The locked ID, relay, API and public key values use OVERWRITE_SETTINGS. This map participates in effective reads, writes and the native fixed-option query used by Flutter. HARD_SETTINGS and BUILTIN_SETTINGS have different consumers. A filename cannot supply a replacement server in the Windows build. The ID/Relay dialog displays the effective profile. [Effective configuration](https://github.com/rustdesk/hbb_common/blob/229b904508364c8997aad0fb5af57effac859f60/src/config.rs#L1215-L1263) · [Fixed-option query](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/ui_interface.rs#L214-L230)

Manual and background update discovery are disabled for this distribution. [Upstream version discovery](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/common.rs#L1020-L1078) · [Desktop updater](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/updater.rs#L88-L101)

Rebase each patch on a new tag in order, review its public dependencies and rerun both builds before changing these pins. [Upstream build workflow](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/.github/workflows/flutter-build.yml)
