# Upstream history

| Date | Component | Pin |
| --- | --- | --- |
| 2026-11-07 | RustDesk 1.5.0 | fada664df7a294d1d1a9ca3e7cd3637069122f17 |
| 2026-11-07 | hbb_common from that tree | 229b904508364c8997aad0fb5af57effac859f60 |

The Flutter title reads the native application name. Android retains its upstream Java namespace for JNI and changes the installable application ID. The app's About views link to the distribution source. [Flutter app title](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/flutter/lib/main.dart#L498-L500)

The locked ID, relay, API and public key values use OVERWRITE_SETTINGS. This map participates in effective reads, writes and the native fixed-option query used by Flutter. HARD_SETTINGS and BUILTIN_SETTINGS have different consumers. A filename cannot supply a replacement server in the Windows build. The ID/Relay dialog displays the effective profile. [Effective configuration](https://github.com/rustdesk/hbb_common/blob/229b904508364c8997aad0fb5af57effac859f60/src/config.rs#L1215-L1263) · [Fixed-option query](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/ui_interface.rs#L214-L230)

Manual and background update discovery are disabled for this distribution. [Upstream version discovery](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/common.rs#L1020-L1078) · [Desktop updater](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/updater.rs#L88-L101)

Rebase each patch on a new tag in order, review its public dependencies and rerun both builds before changing these pins. [Upstream build workflow](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/.github/workflows/flutter-build.yml)

## Encrypted sessions and locked network capabilities

The native session loop and both forwarding protocols finish checking stream encryption before login. This distribution rejects a failed check immediately and presents a non-retryable error. Direct address connections use an upstream raw TCP path and are refused before dialing. The desktop and mobile Flutter clients receive the existing error dialog with a single acknowledgement. [Direct address transport](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/client.rs#L424-L455) · [Session encryption gate](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/client/io_loop.rs#L209-L231) · [Forwarding gates](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/port_forward.rs#L173-L186) · [Multiplexed forwarding](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/port_forward.rs#L415-L427)

All four options are fixed to `N` in `OVERWRITE_SETTINGS`. Network → ID/Relay server displays their effective values. On Windows, Security shows the following locked controls. [Option names](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/libs/base/src/config/keys.rs#L35-L60) · [Fixed checkbox behavior](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/flutter/lib/desktop/pages/desktop_setting_page.dart#L2656-L2714)

| Option | Windows Security control | Enforcement |
| --- | --- | --- |
| `direct-server` | Enable direct IP access, unchecked; port field hidden | The host skips its direct TCP listener. |
| `enable-lan-discovery` | Deny LAN discovery, checked | The discovery listener and active search skip socket creation. |
| `enable-tunnel` | Enable TCP tunneling, unchecked | Incoming tunnel authorization honors the locked value before central grants or the Full Access preset. Outgoing forwarding stops before binding a local port. |
| `allow-remote-config-modification` | Enable remote configuration modification, unchecked | The settings input guard honors the locked value before session grants or the Full Access preset. |

The preset display honors fixed values, including in Full Access mode. Signed custom settings also preserve the four disabled options. [Upstream tunnel authorization](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/server/connection.rs#L2628-L2676) · [Remote settings input guard](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/flutter/lib/common.dart#L3138-L3160) · [LAN discovery directions](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/lan.rs#L27-L83)


### Permanent password provisioning

The installed administrative setter accepts a bounded UTF-8 line through stdin, clears the read buffer, and waits for the service to acknowledge the IPC update. The portable wrapper preserves standard handles and waits for this command. The installer resource identifies the package as SteadDesk. [Core command](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/core_main.rs#L437-L457) · [IPC setter](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/ipc.rs#L1734-L1771) · [Portable launcher](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/libs/portable/src/main.rs#L230-L259)

The Windows package embeds the native runner as `SteadDesk.exe`. The EXE installer copies the payload directory as-is and the service registration resolves the installed executable from the application name. [Payload copy](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/platform/windows.rs#L1452-L1489) · [Service registration](https://github.com/rustdesk/rustdesk/blob/fada664df7a294d1d1a9ca3e7cd3637069122f17/src/platform/windows.rs#L3942-L3970)
