# UPD-4 Windows platform component: focused checks

The public component is `windows-fleet/fleet_installer.cpp` with its C ABI header.
Its caller handles the protocol, scheduling, J23, session and transaction logic.
The component contains Windows trust/file/service/process checks and the reviewed
branded EXE `--silent-install` invocation only. It does not install an Agent, change
passwords, elevate itself, uninstall, reset data or reboot Windows.

## Observed local results

`python3 windows-fleet/tests/run-local.py` completed successfully:

- **35** portable C++ path and ABI checks passed with the host compiler. They cover
  drive-absolute paths, UNC/device/ADS rejection, traversal and empty components,
  trailing dots/spaces, constrained artifact names, DOS device names and fixed C ABI
  sizes/offsets.
- The complete production and isolated-test Windows C++ components compiled with
  MinGW x64, C++17, `-Wall -Wextra -Werror`.
- Both variants linked into genuine PE executables against `wintrust`, `crypt32`,
  `bcrypt`, `advapi32`, `version`, `shell32`, `ole32` and `uuid`.
- Object-symbol checks found the required production ABI and proved that the
  `sd_fleet_test_prepare` admission bypass is absent from production.
- `git diff --check` passed. Distribution test discovery passed **26 tests** at
  this worktree snapshot.
- C++ and header formatting used the isolated pinned `clang-format 18.1.8` tool.

These checks were run on macOS. **No Windows executable was executed by these
checks.** They do not establish successful WinVerifyTrust, ACL enforcement, SCM
ancestry, actual installer exits, a reboot, full application linkage or merchant
acceptance. The independent Windows fixture and its returned receipts own those
runtime results.

## Implemented boundaries reviewed in source

The fixed Known Folder path is opened from drive root through all parents before
opening the artifact. Parent handles deny delete sharing; artifact access denies
write/delete sharing. App directories and artifacts reject unsafe owners, broad
mutating ACLs, reparse points, remote/device paths and hard links. Standard ancestor
create-child/attribute grants are not mistaken for permission to replace the held
private descendants. Existing unsafe app directories are refused rather than fixed.

Preparation hashes the held bytes, invokes actual WinVerifyTrust Authenticode
policy and chain checks, compares the verified leaf certificate SHA-256, checks
brand/version/AMD64 PE metadata, then derives the strict signed-wrapper payload
binding. Verification happens before the short online permit. Launch keeps the
lease held, performs cheap size/handle-path checks, and uses an explicit executable
path with one fixed argument. No slow second full-file hash can consume the permit
at the irreversible launch boundary.

The current service is an observed existing baseline, not a signed release
endorsement. Actual worker admission requires positive SCM parent-process ownership
and protected canonical images. Readback requires a replacement service process,
actual brand/build and installed binary digest equal to the durable digest derived
from authenticated `SteadDeskPayloadSHA256`. Outer and inner digests are separate.
Absent/malformed/wrong binding cannot become verified health.

Actual process exits 0, 3010 and failure codes remain distinct. Unknown completion
requires retaining the protected lease and manual/reconciliation handling. The
3010 reboot identifier comes from the kernel boot-environment GUID, not wall-clock
arithmetic; an unsupported or unavailable query holds the transaction.

## Explicit compatibility limits

Only the reviewed branded SteadDesk EXE path is approved. There is no approved
SteadDesk MSI catalog identity; the existing documented MSI product is different.
Every MSI is rejected with `SD_FLEET_MSI_NOT_APPROVED`. No synthetic MSI exception,
production trust bypass or MSI execution success is claimed. x64 and exact branded
1.5.0.N builds are required. Full Windows CI, service-backed update/recovery,
certificate/network behavior and production approval remain separate gates.
