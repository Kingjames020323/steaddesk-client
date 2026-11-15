# Windows merchant installation platform boundary

This C++17 component is used only by the opt-in Windows merchant fleet worker. It
implements Windows file, trust, process and existing-service checks. It has no
network client, release authority, identity-key export, updater service, self
elevation, Agent installer, password operation, uninstall, data reset or reboot.
Its caller remains responsible for signed-manifest verification, current device
proof, store window, J23, sessions, frequency limits, durable transaction/outbox,
fresh online safety permit and `install_authorized=true` immediately before launch.

## Files and ABI

`fleet_installer.h` defines the C ABI. The enabled build copies it and
`fleet_installer.cpp` together into the patched source. Compile C++17 with
`UNICODE`, `_UNICODE`, `NOMINMAX`, `_WIN32_WINNT=0x0602`; link `wintrust`, `crypt32`,
`bcrypt`, `advapi32`, `version`, `shell32`, `ole32` and `uuid`. The normal Windows
compiler's C++ exception runtime is required. No exception crosses the ABI; output
structures are cleared before use and failures return stable status codes.

`SdFleetExpected` is constructed from the already authenticated manifest:
artifact leaf, exact size, outer SHA-256, leaf signer-certificate SHA-256,
`versionCode`, and architecture. Only x64 is currently supported. The signed
release build must match the actual fixed PE file/product tuple **1.5.0.N**, with
`versionCode=N`, not Android's separate version-code offset.

`sd_fleet_private_directory` derives the fixed local
`ProgramData\SteadDesk\fleet-update` through Windows Known Folders. It creates only
the app-owned directories with a protected SYSTEM/Administrators DACL, and never
repairs or replaces an existing unsafe directory. Preparation opens and retains
handles from the fixed drive root through every parent and the artifact. Remote
volumes, UNC/device/ADS paths, traversal, reparse points, unsafe names, hard links,
untrusted owners and broad write/delete/control ACLs on the app-owned directories
and artifact are rejected. Standard ancestor create-child/attribute grants are
allowed only while their ACL denies untrusted delete-child, ownership and DACL
control and their no-delete handles remain held. Precreated unsafe app directories
are rejected. Parent handles
deny delete sharing; the artifact handle denies write and delete sharing.

`sd_fleet_prepare` verifies the exact held file size and SHA-256, genuine
`WinVerifyTrust` Authenticode policy with chain revocation checks, and the leaf
certificate's SHA-256 from the successfully verified signer chain. It checks actual
AMD64 PE identity, the exact merchant ProductName `SteadDesk`, fixed version tuple
and strict version increase over the observed installed service. No server-supplied
path, executable name, command or trust root is accepted.

## Payload binding and existing service

The real branded EXE is a wrapper, so its outer hash is not the installed binary's
hash. After authenticating the locked outer, preparation reads the strict lowercase
64-hex VERSIONINFO string `SteadDeskPayloadSHA256`. All resource translations must
agree. Missing metadata uses the outer hash conservatively, allowing only a proven
same-binary result; malformed or conflicting metadata rejects preparation.
`sd_fleet_payload_digest` exposes the derived digest for the caller's durable
transaction. A caller-provided payload hash never replaces this derivation during
preparation. The packaging workflow must insert the exact inner merchant binary's
hash before the outer receives its Authenticode signature.

The existing merchant service is **SteadDesk**, with the quoted fixed image
`ProgramFiles\SteadDesk\SteadDesk.exe --service`. SCM must report its own process
running; its actual process image and protected installed path must agree. The
updater must itself be the installed service-owned `--server` child: its parent PID
must equal the running SCM process and its creation time must follow that parent.
This corresponds to the existing service's direct `CreateProcessAsUserW` child.
The companion must be exactly one running existing SCM service whose protected
image resolves to `ProgramFiles\Mesh Agent\MeshAgent.exe`. Unknown, absent, stopped
or ambiguous services hold installation; this component never changes them.

`sd_fleet_current_service` returns an **observed baseline**, not an endorsement of a
signed release. The first installed inner binary may not itself be separately
Authenticode-signed. The caller should compare this observation with the previously
managed payload digest when one exists; baseline observation alone cannot mark a
new attempt healthy.

## Launch, results and recovery

Preparation happens before acquiring the short online permit. The held lease keeps
the verified object and its parent paths protected. `sd_fleet_launch` performs only
cheap size/final-handle-path checks, then calls `CreateProcessW` with an explicit
application path and the sole reviewed argument `--silent-install`. It uses no
shell, inherited handles or elevation and cannot launch the same lease twice.
The caller must recheck local gates and permit expiry immediately before this
boundary, after any expensive verification or SCM checks.

The actual process exit code is returned separately from platform-call success:
**0**, **3010**, and other codes remain distinct. The wrapper may spawn its real
installer and exit, so exit 0 is only launch/process evidence. An unknown wait never
authorizes a retry. On `SD_FLEET_WAIT`, the caller retains the lease while the
transaction may still be in flight, preserving its protected handles.

`sd_fleet_readback` requires a replacement SCM service process (PID plus creation
time), protected canonical path, actual merchant brand/version/architecture and
actual installed-binary SHA-256 equal to the durable payload digest derived from
the authenticated outer. An independently signed inner is unnecessary when this
exact signed-wrapper binding holds. Wrong or unavailable payload identity returns
`SD_FLEET_PAYLOAD_UNPROVEN`, and cannot be promoted to health. The companion service
must also remain running. The returned binary digest is distinct from the original
outer artifact hash used in the ops protocol.

For 3010, the caller must retain `pending_reboot` until a changed kernel boot
identifier is independently observed. `sd_fleet_boot_id` uses the kernel's boot
environment GUID, hashes its 16 bytes with SHA-256 and returns the first 64 bits.
It does not derive boot identity from wall-clock time, uptime arithmetic or an
installer exit. Missing/unsupported/zero boot identity holds the transaction.

## Explicit MSI restriction

There is no approved branded SteadDesk MSI product identity in the reviewed input.
The documented MSI lane belongs to a different product. Consequently **all MSI
inputs fail closed with `SD_FLEET_MSI_NOT_APPROVED`**, including test admission.
This change does not invent an approved MSI identity or reuse the other product's
catalog. An MSI execution lane needs separately reviewed product/catalog identity;
its eventual command must use the absolute system `msiexec /i … /qn /norestart`.
No MSI installation or MSI return-code acceptance is claimed here.

## Focused verification and test boundaries

`python3 windows-fleet/tests/run-local.py` runs 35 real portable path/ABI checks,
then cross-compiles and links both production and isolated test variants when
MinGW is available. It checks that `sd_fleet_test_prepare` is absent from production
symbols. These checks do not execute Windows code or validate Windows trust.

`SD_FLEET_TEST_BUILD` changes only fixed test service/directory identities and adds
`sd_fleet_test_prepare`, which bypasses live merchant/Agent/worker ancestry admission
so the isolated fixture can execute the genuine trust/file/launch layer. The test
paths are `SteadDeskFleetTest` and `SteadDeskFleetTestAgent`; there is no arbitrary
runtime path or service override. Test admission is absent from production builds.
The separate Windows fixture owns self-signed packages, temporary test trust and
actual process/service checks; only its returned receipts establish Windows results.

Primary API references: [WinVerifyTrust](https://learn.microsoft.com/en-us/windows/win32/api/wintrust/nf-wintrust-winverifytrust),
[WINTRUST_FILE_INFO](https://learn.microsoft.com/en-us/windows/win32/api/wintrust/ns-wintrust-wintrust_file_info),
[GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo).
