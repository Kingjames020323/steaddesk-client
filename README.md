# SteadDesk

SteadDesk is an AGPL-3.0 remote support client based on RustDesk 1.5.0 for Windows x64 and Android (arm64-v8a, armeabi-v7a and x86_64). Clone with `git clone --recurse-submodules` and run `bash scripts/apply-patches.sh` before building in `upstream/`. The script checks the pinned upstream revisions. [Source pins and patch notes](UPSTREAM.md)

## Release procedure

1. Update `RELEASE_VERSION` by pull request. Start at `1.5.0-sd.1` and increase the final number for each release. The version appears in Windows file properties, About and Android's versionName. The installed Windows CLI continues to print `1.5.0` for `--version` so existing provisioning scripts can verify the upstream protocol. Review the PR build, including the offline Windows tests and the assembled release bundle.
2. After review and merge, the release owner tags the reviewed commit with the exact version from `RELEASE_VERSION`. For example, push `v1.5.0-sd.1` to trigger the release build. CI checks the tag against the file, builds unsigned Windows and Android packages, and attaches both packages, the patched source archive and `SHA256SUMS` to a **draft** GitHub Release. A pull request or manual CI run produces a downloadable `Unsigned-release` artifact. If a draft upload was interrupted, inspect the existing draft and reconcile its assets before retrying.
3. Jason downloads all four draft assets into an empty directory named `unsigned`, copies them to the signing workstation and checks the hashes. Run `sha256sum -c SHA256SUMS` inside that directory, or `shasum -a 256 -c SHA256SUMS` on macOS. Keep the signing tools from the same reviewed tag. Each signing step takes a complete four-file bundle and writes to a new directory under an existing parent. Use Python 3.10+, PowerShell 7 and Windows SDK SignTool 10.0.22000 or later on Windows, and Bash plus Android SDK Build-Tools 35 or later on the Android signing host. The Windows tool accepts an RSA code-signing PFX and verifies the publisher trust chain.
4. On Windows, run the command below. Use the local or removable drive containing the PFX. The tool prompts for its password, signs with SHA-256, time-stamps the signature, verifies it and writes a new bundle. RFC 3161 timestamping requires access to the chosen timestamp service; an isolated workstation can use a reachable internal timestamp service via `-TimestampUrl`.

   ```powershell
   ./scripts/sign-windows.ps1 -ReleaseDir ./unsigned -OutputDir ./windows-signed -PfxPath E:\release.pfx
   ```

5. Transfer the complete Windows-signed bundle to the Android signing workstation. Run the command below with the keystore path and key alias. The tool prompts for signing credentials, verifies the APK and prints the signing certificate. Compare the certificate identity with the release owner's trusted record. The signed bundle includes the Windows EXE, APK, corresponding source and a new `SHA256SUMS`.

   ```bash
   scripts/sign-android.sh ./windows-signed ./signed /media/usb/release.jks release
   (cd signed && sha256sum -c SHA256SUMS)
   ```

6. Jason uploads the signed EXE, signed APK and final checksum file to the **existing draft**. Keep the verified source archive and remove the two unsigned draft assets. Download the four final assets into a fresh directory and verify `SHA256SUMS` again. Claude reviews the version, signatures, checksums and source archive. The release owner publishes the draft after that review.

Tag builds do not restore the three GitHub caches that pull request builds write: the Rust caches (`Swatinem/rust-cache` is skipped), the Flutter SDK cache, and the vcpkg binary cache (`VCPKG_BINARY_SOURCES` is `clear`; `run-vcpkg` also stops caching its own tool checkout). This does not cover tools that come with the runner image or downloads during the build. The signing tools are tested end to end with throwaway keys by the `Signing tools self-test` workflow, which runs when the tools change and can be started by hand before a release.

### Version numbers

`1.5.0-sd.N` has these effects, checked against the pinned upstream source:

- **Android upgrade order.** `versionName` is `1.5.0-sd.N` and `versionCode` is 68 + N (patch 0007). Android refuses to install a lower `versionCode` over a higher one, so N must only go up.
- **Windows file version.** The file and product version resources are 1.5.0.N.
- **About pages.** `main_get_version` returns the release version; in the pinned Dart source its only caller is the desktop About page.
- **Not the peer protocol.** The version a client sends to the other side is `crate::VERSION`, which these patches do not change, so it stays `1.5.0`. The protocol checks that were found (`versionCmp` in Dart and `get_version_number` in Rust on the peer's version) see `1.5.0`.
- Upstream also compares its own version with the newest RustDesk release to offer updates; patch 0003 turns that path off.

A future patch that compares the release version must parse the `-sd.N` suffix itself.

### Protecting release tags

A pushed `v1.5.0-sd.*` tag starts the release build, so only the release owner may create one. In the repository's **Settings → Rules → Rulesets**, Jason creates a tag ruleset:

- Name `Release tags`, enforcement **Active**.
- Target tags: include the pattern `v*`.
- Rules: **Restrict creations**, **Restrict updates**, **Restrict deletions**, and **Block force pushes**.
- Bypass list: **Repository admin** only. In this personal repository that is Jason alone; do not give anyone else the admin role. Collaborators with write access, GitHub Actions and Codex cannot create, move or delete `v*` tags.

After saving, open the ruleset again and confirm it is **Active** and targets `v*`.

Store the signing material on the signing workstation or its removable media. The workflow only needs a GitHub token to create the draft. Windows builds without a publisher signature and unsigned APKs are staging artifacts; Android installation requires a signed APK. Earlier demo APKs used a temporary signing certificate, so Android may reject an in-place upgrade to the offline-signed release.

The source archive includes the distribution tools, patches and the patched upstream source with its pinned submodules. After extraction the source under `upstream/` is already patched. Hosted runner images, OS packages, Flutter dependency resolution and upstream's custom Windows engine download can vary between runs. Verify the assets from the release under test.
