# SteadDesk

SteadDesk is a remote support client based on RustDesk 1.5.0. This distribution targets Windows x64 and Android (arm64-v8a, armeabi-v7a and x86_64). It keeps the upstream remote control engine and publishes its changes as a numbered patch queue under AGPL-3.0.

Clone with Git submodules and run `bash scripts/apply-patches.sh` before building in `upstream/`. The script checks both source revisions before applying changes. Run it again to verify an already patched tree. See [UPSTREAM.md](UPSTREAM.md) for the source pins and downstream choices.

The Actions build produces a Windows executable and a universal APK, each bundled with SHA256SUMS. Use the Windows executable's normal install dialog. Windows has no publisher signature at this stage. Android uses the ephemeral runner's debug keystore; a later demo may require uninstalling the earlier build. Intermediate native and bridge files expire after one day. There is no automatic update channel.

Builds use the pinned RustDesk workflow's Flutter and Rust toolchains and vcpkg baseline. Hosted runner images, OS packages, Flutter pub resolution, upstream's custom Windows engine download, and the transient Android debug certificate can vary between runs. Verify the checksum from the specific workflow run you downloaded.
