# Isolated Windows fleet verification

Run the platform fixture **only on a fresh disposable Windows x64 GitHub-hosted runner**:

```powershell
pwsh -NoLogo -NoProfile -File .distribution/scripts/tests/windows-fleet/run.ps1 -RepoRoot .distribution
```

The script refuses non-Windows, non-GitHub and non-x64 environments. It compiles
the actual candidate C++ ABI with `SD_FLEET_TEST_BUILD`, which changes only fixed
lab prefixes and exposes a preparation seam bypassing the existing merchant
service/parent gate. Authenticode, expected signer/hash/size/version/product,
protected file handles and process launch remain actual candidate code.

The fixture generates nonexportable disposable code-signing certificates in the
runner's current-user certificate store. Only those exact certificates are
trusted in current-user Root, and their exact thumbprints/private keys are
removed in `finally`. It never changes macOS trust. All generated packages and
keys stay outside the checkout. No timestamp server is contacted.

It exercises actual trusted/tampered/other-signer packages, product/version and
path/ACL/hardlink rejection, signed inner-payload binding, protected-handle
replacement denial, exactly-once launches and real mock process exits 0, 3010
and 1603. Synthetic SCM services exist only under the fixed test prefixes
`SteadDeskFleetTest` and `SteadDeskFleetTestAgent`; they are removed after tests.
These services are test identity/readback fixtures, not the merchant application
or Mesh Agent. The fixture does not reset passwords, deploy an agent, uninstall
or change production service state. Pre-existing test paths/services abort the
run before mutation.

The signed outer VERSIONINFO field `SteadDeskPayloadSHA256` is built from the
actual signed inner fixture hash. Correct, wrong, malformed and missing fields
are tested. A missing field supports only identical outer/installed bytes; it
cannot authorize a distinct inner payload. Unapproved MSI is rejected by the
shipping platform policy, with no caller flag to override it.

The sanitized native receipt is written to:

```text
$env:RUNNER_TEMP\steaddesk-fleet-windows-receipt.json
```

A passing script also verifies owned paths/services and exact test certificate
removal. Actual Windows acceptance depends on this script's successful hosted
run; parser or cross-compile success does not satisfy it.

The portable production controller has separate mock-boundary tests:

```sh
python .distribution/scripts/tests/windows-fleet/run-controller.py \
  --repo-root .distribution --source-root .
```

This requires Python 3.11+, Rust and initialized patched upstream dependencies.
It reuses the upstream pinned lockfile and git patches. `--common-root` and
`--lock-file` support isolated development checkouts. Tests import the real
candidate module and real hbb_common cryptography; only the Host's platform and
HTTP operations are explicitly mocked. The actual WindowsHost compile probe is
a separate CI check. `run.ps1` does not invoke either Rust check automatically.

Local non-Windows generation can prove real PE/AuthentiCode cryptography without
executing Windows APIs:

```sh
python scripts/tests/windows-fleet/run-local.py \
  --osslsigncode /external/tools/osslsigncode --output /external/evidence.json
```

This uses MinGW and OpenSSL to generate/sign real AMD64 PE fixtures. It verifies
five signed resource vectors and rejects a modified signed `.text` section.
Keys and every generated binary are destroyed with the temporary directory.
It does **not** prove WinVerifyTrust, native installation, service identity or
Windows trust-store behavior. See `EVIDENCE-local.json` for the observed local
results and explicit Windows NOT_RUN boundary.
