[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RepoRoot)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Run only in a disposable Windows GitHub-hosted test job; no office or physical machines.'
}
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') { throw 'UPD-4 platform acceptance requires native Windows x64.' }
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Disposable fixture requires administrator only for its isolated test services/directories.' }
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$fixture = Join-Path $RepoRoot 'scripts/tests/windows-fleet'
$platform = Join-Path $RepoRoot 'windows-fleet'
$lab = Join-Path ([IO.Path]::GetTempPath()) ('SteadDeskFleetFixture-' + [guid]::NewGuid().ToString('N'))
$stagingBase = Join-Path $env:ProgramData 'SteadDeskFleetTest'
$installBase = Join-Path $env:ProgramFiles 'SteadDeskFleetTest'
$agentBase = Join-Path $env:ProgramFiles 'SteadDeskFleetTestAgent'
$serviceNames = @('SteadDeskFleetTest','SteadDeskFleetTestAgent')
foreach ($path in @($stagingBase,$installBase,$agentBase)) { if (Test-Path -LiteralPath $path) { throw "Preserve pre-existing test path: $path" } }
foreach ($name in $serviceNames) { if (Get-Service -Name $name -ErrorAction SilentlyContinue) { throw "Preserve pre-existing service: $name" } }
New-Item -ItemType Directory -Path $lab | Out-Null
$certificates = [Collections.Generic.List[string]]::new()
$createdServices = [Collections.Generic.List[string]]::new()
$cases = [Collections.Generic.List[object]]::new()
$stage = $null
$probe = Join-Path $lab 'platform-probe.exe'
$receipt = Join-Path $env:RUNNER_TEMP 'steaddesk-fleet-windows-receipt.json'

function Run([string]$Exe,[string[]]$Arguments) {
    $lines = @(& $Exe @Arguments 2>&1)
    $code = $LASTEXITCODE
    $lines | ForEach-Object { Write-Host $_ }
    if ($code -ne 0) { throw "Fixture command failed ($code): $Exe" }
    return $lines
}
function Digest([string]$Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function New-TestCertificate([string]$Name) {
    Write-Host "Generating a disposable signing key."
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject ('CN=' + $Name) -CertStoreLocation 'Cert:\CurrentUser\My' -HashAlgorithm SHA256 -KeyAlgorithm RSA -KeyLength 2048 -Provider "Microsoft Software Key Storage Provider" -KeyExportPolicy NonExportable -NotAfter ([datetime]::UtcNow.AddDays(1))
    $certificates.Add($cert.Thumbprint)
    Write-Host "Installing the public certificate in the disposable runner trust store."
    $store = [Security.Cryptography.X509Certificates.X509Store]::new('Root','LocalMachine')
    $public = [Security.Cryptography.X509Certificates.X509Certificate2]::new($cert.RawData)
    try {
        $store.Open([Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $store.Add($public)
    } finally {
        $store.Close()
        $public.Dispose()
    }
    Write-Host "Disposable signing certificate is ready."
    return $cert
}
function Sign-Test([string]$Path,$Certificate) {
    $result = Set-AuthenticodeSignature -FilePath $Path -Certificate $Certificate -HashAlgorithm SHA256
    if ($result.Status -ne 'Valid') { throw "Self-signed lab package did not verify: $($result.Status)" }
}
function Build-Fixture([string]$Name,[string]$Payload='',[string]$Product='SteadDesk') {
    $rc = Join-Path $lab ($Name + '.rc')
    $res = Join-Path $lab ($Name + '.res')
    $exe = Join-Path $lab ($Name + '.exe')
    $prefix = "#define FIXTURE_BUILD 70`n#define FIXTURE_VERSION_TEXT `"1.5.0.70`"`n#define FIXTURE_PRODUCT_NAME `"$Product`"`n#define FIXTURE_DESCRIPTION `"SteadDesk Fleet Fixture $Name`"`n"
    if ($Payload) { $prefix += "#define SD_UPD4_PAYLOAD_SHA `"$Payload`"`n" }
    [IO.File]::WriteAllText($rc,$prefix + [IO.File]::ReadAllText((Join-Path $fixture 'fixture.rc')),[Text.UTF8Encoding]::new($false))
    Run 'rc.exe' @('/nologo',('/fo' + $res),$rc) | Out-Null
    Run 'cl.exe' @('/nologo','/TC','/W4','/D_CRT_SECURE_NO_WARNINGS',('/Fo' + (Join-Path $lab ($Name+'.obj'))),(Join-Path $fixture 'installer_fixture.c'),('/Fe' + $exe),'/link',$res,'advapi32.lib') | Out-Null
    Sign-Test $exe $script:certificate
    return $exe
}
function Stage-File([string]$Source,[string]$Leaf) { Copy-Item -LiteralPath $Source -Destination (Join-Path $stage $Leaf) }
function Probe([string]$Name,[string]$Action,[string]$Leaf,[string]$Source,[string]$Payload,[int]$Expected=0,[int]$ExitCode=0,[uint32]$PriorPid=0,[uint64]$PriorCreated=0,[int]$Version=70,[string]$Signer='') {
    if (-not $Signer) { $Signer=$script:signer }
    $argsList = @($Action,$Leaf,([string](Get-Item -LiteralPath $Source).Length),([string]$Version),(Digest $Source),$Signer,$Payload,([string]$Expected),([string]$ExitCode))
    if ($Action -eq 'readback') { $argsList += @([string]$PriorPid,[string]$PriorCreated) }
    $lines = @(Run $probe $argsList)
    $cases.Add([ordered]@{name=$Name;expected_status=$Expected;expected_exit=$ExitCode;native=@($lines | ForEach-Object { $_.ToString() } | Where-Object { $_.StartsWith('{') } | ForEach-Object { $_ | ConvertFrom-Json })})
}
function Private-Directory([string]$Path) {
    New-Item -ItemType Directory -Path $Path | Out-Null
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true,$false)
    foreach ($id in @('S-1-5-18','S-1-5-32-544')) {
        $sid=[Security.Principal.SecurityIdentifier]::new($id)
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}
function Start-TestService([string]$Name,[string]$Path) {
    $created=New-Service -Name $Name -BinaryPathName ('"' + $Path + '" --service') -StartupType Manual
    $created.Dispose()
    $createdServices.Add($Name)
    Start-Service -Name $Name
    $controller=Get-Service -Name $Name
    try { $controller.WaitForStatus('Running',[timespan]::FromSeconds(15)) } finally { $controller.Dispose() }
}
function Restart-TestService {
    Restart-Service -Name 'SteadDeskFleetTest'
    $controller=Get-Service -Name 'SteadDeskFleetTest'
    try { $controller.WaitForStatus('Running',[timespan]::FromSeconds(15)) } finally { $controller.Dispose() }
}
try {
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue) -or -not (Get-Command rc.exe -ErrorAction SilentlyContinue)) {
        $vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
        $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($LASTEXITCODE -ne 0 -or -not $vs) { throw 'Visual C++ tools are required.' }
        $devShell = Join-Path $vs 'Common7/Tools/Launch-VsDevShell.ps1'
        & $devShell -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
        Get-Command cl.exe,rc.exe -CommandType Application -ErrorAction Stop | Out-Null
    }
    Run 'cl.exe' @('/nologo','/std:c++17','/EHsc','/W4','/DSD_FLEET_TEST_BUILD=1',('/I'+$platform),('/Fo'+$lab+'\'),(Join-Path $platform 'fleet_installer.cpp'),(Join-Path $fixture 'platform_probe.cpp'),('/Fe'+$probe),'/link','bcrypt.lib','wintrust.lib','crypt32.lib','advapi32.lib','version.lib','shell32.lib','ole32.lib','uuid.lib') | Out-Null
    $directoryLines = @(Run $probe @('directory'))
    $directory = ($directoryLines | Where-Object { $_.ToString().StartsWith('{') } | Select-Object -Last 1 | ConvertFrom-Json)
    $stage = $directory.directory
    if ($stage -ne (Join-Path $stagingBase 'fleet-update')) { throw 'Candidate returned unexpected private staging path.' }
    $script:certificate=New-TestCertificate ('SteadDesk Fleet Fixture '+[guid]::NewGuid().ToString('N'))
    $script:signer=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($certificate.RawData)).ToLowerInvariant()
    $otherCertificate=New-TestCertificate ('SteadDesk Other Fixture '+[guid]::NewGuid().ToString('N'))
    $other=Build-Fixture 'other-signer'
    Sign-Test $other $otherCertificate
    $inner=Build-Fixture 'inner'
    $innerHash=Digest $inner
    $outer=Build-Fixture 'outer' $innerHash
    $wrong=Build-Fixture 'wrong-binding' ('0'*64)
    $missing=Build-Fixture 'missing-binding'
    $malformed=Build-Fixture 'malformed-binding' 'not-a-sha256'
    $product=Build-Fixture 'wrong-product' $innerHash 'OtherProduct'
    Stage-File $outer 'candidate.exe'
    Probe 'trusted correct wrapper and signed inner binding' 'verify' 'candidate.exe' $outer $innerHash
    Stage-File $other 'other-signer.exe'
    Probe 'other trusted signing certificate rejected' 'verify' 'other-signer.exe' $other (Digest $other) 4
    Probe 'wrong expected signer rejected' 'verify' 'candidate.exe' $outer $innerHash 4 0 0 0 70 ('0'*64)
    Probe 'wrong target numeric version rejected' 'verify' 'candidate.exe' $outer $innerHash 7 0 0 0 69
    Stage-File $product 'product.exe'
    Probe 'wrong product rejected' 'verify' 'product.exe' $product $innerHash 6
    Stage-File $malformed 'malformed.exe'
    Probe 'malformed signed payload binding rejected' 'verify' 'malformed.exe' $malformed $innerHash 6
    Probe 'traversal rejected' 'verify' '..\candidate.exe' $outer $innerHash 2
    Probe 'ADS rejected' 'verify' 'candidate.exe:stream' $outer $innerHash 2
    Stage-File $outer 'candidate.msi'
    Probe 'unapproved MSI cannot be enabled by caller' 'verify' 'candidate.msi' $outer $innerHash 11
    $tampered=Join-Path $lab 'tampered.exe'
    $bytes=[IO.File]::ReadAllBytes($outer)
    $pe=[BitConverter]::ToInt32($bytes,0x3c)
    $sections=[BitConverter]::ToUInt16($bytes,$pe+6)
    $optional=[BitConverter]::ToUInt16($bytes,$pe+20)
    $found=$false
    for ($i=0;$i -lt $sections;$i++) {
        $at=$pe+24+$optional+40*$i
        if ([Text.Encoding]::ASCII.GetString($bytes,$at,8).Trim([char]0) -eq '.text') { $raw=[BitConverter]::ToUInt32($bytes,$at+20); $bytes[$raw+16]=$bytes[$raw+16] -bxor 1; $found=$true; break }
    }
    if (-not $found) { throw 'PE .text section missing.' }
    [IO.File]::WriteAllBytes($tampered,$bytes)
    Stage-File $tampered 'tampered.exe'
    Probe 'tampered signed image fails real Authenticode with matching changed file hash' 'verify' 'tampered.exe' $tampered $innerHash 4
    Stage-File $tampered 'candidate.exe'
    Probe 'artifact mismatch rejected before launch' 'verify' 'candidate.exe' $outer $innerHash 5
    Stage-File $outer 'candidate.exe'
    $linked=Join-Path $stage 'linked.exe'
    New-Item -ItemType HardLink -Path $linked -Target (Join-Path $stage 'candidate.exe') | Out-Null
    try { Probe 'hardlinked candidate rejected' 'verify' 'linked.exe' $outer $innerHash 2 } finally { Remove-Item -LiteralPath $linked -Force }
    $candidatePath=Join-Path $stage 'candidate.exe'
    $originalAcl=Get-Acl -LiteralPath $candidatePath
    $unsafeAcl=Get-Acl -LiteralPath $candidatePath
    $unsafeAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new('S-1-5-32-545'),'Modify','Allow'))
    Set-Acl -LiteralPath $candidatePath -AclObject $unsafeAcl
    try { Probe 'untrusted writable candidate rejected' 'verify' 'candidate.exe' $outer $innerHash 3 } finally { Set-Acl -LiteralPath $candidatePath -AclObject $originalAcl }
    foreach ($exitCode in @(0,3010,1603)) {
        $env:SD_UPD4_FIXTURE_EXIT=[string]$exitCode
        $env:SD_UPD4_FIXTURE_RECEIPT=Join-Path $lab ('installer-'+$exitCode+'.jsonl')
        Probe ('actual mocked installer exit '+$exitCode+' / held handle / exactly once') 'launch' 'candidate.exe' $outer $innerHash 0 $exitCode
        if (@(Get-Content -LiteralPath $env:SD_UPD4_FIXTURE_RECEIPT).Count -ne 1) { throw 'Installer executed more than once.' }
    }
    # Two synthetic SCM services only under the test build's fixed paths.
    Private-Directory $installBase
    Private-Directory $agentBase
    $installed=Join-Path $installBase 'SteadDesk.exe'
    $agent=Join-Path $agentBase 'MeshAgent.exe'
    Copy-Item -LiteralPath $inner -Destination $installed
    Copy-Item -LiteralPath $inner -Destination $agent
    Start-TestService 'SteadDeskFleetTest' $installed
    Start-TestService 'SteadDeskFleetTestAgent' $agent
    $currentLines=@(Run $probe @('current'))
    $prior=$currentLines | Where-Object { $_.ToString().StartsWith('{') } | Select-Object -Last 1 | ConvertFrom-Json
    Probe 'same running process is not update readback' 'readback' 'candidate.exe' $outer $innerHash 8 0 $prior.pid $prior.created
    Restart-TestService
    Probe 'replacement process and trusted bound inner hash readback' 'readback' 'candidate.exe' $outer $innerHash 0 0 $prior.pid $prior.created
    Stage-File $wrong 'wrong.exe'
    Probe 'validly signed wrong binding extracted' 'verify' 'wrong.exe' $wrong ('0'*64)
    Probe 'wrong bound inner hash remains unproven' 'readback' 'wrong.exe' $wrong ('0'*64) 13 0 $prior.pid $prior.created
    Stage-File $missing 'missing.exe'
    $missingHash=Digest $missing
    if ($missingHash -eq $innerHash) { throw 'Missing binding fixture must be distinct from installed payload.' }
    Probe 'missing binding is only same-bytes fallback' 'verify' 'missing.exe' $missing $missingHash
    Probe 'missing field cannot authorize a different installed wrapper payload' 'readback' 'missing.exe' $missing $missingHash 13 0 $prior.pid $prior.created
    $output=[ordered]@{platform='actual Windows x64';scope='candidate platform ABI; real Authenticode and CreateProcess; synthetic installer and SCM services; not real merchant health';certificate_sha256=$signer;inner_sha256=$innerHash;outer_sha256=(Digest $outer);source_sha256=@{platform=(Digest (Join-Path $platform 'fleet_installer.cpp'));probe=(Digest (Join-Path $fixture 'platform_probe.cpp'))};cases=$cases;cleanup='finally removes exact certificate thumbprint, owned services and isolated prefixes'}
    [IO.File]::WriteAllText($receipt,($output | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
    Write-Host "Native assertions passed; verifying disposable cleanup."
} finally {
    foreach ($name in $createdServices) {
        try { Stop-Service -Name $name -ErrorAction SilentlyContinue } catch {}
        & sc.exe delete $name | Out-Null
    }
    foreach ($thumb in $certificates) {
        $root = 'Cert:\LocalMachine\Root\' + $thumb
        if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Force }
        $path='Cert:\CurrentUser\My\'+$thumb
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -DeleteKey -Force }
    }
    Remove-Item Env:SD_UPD4_FIXTURE_EXIT -ErrorAction SilentlyContinue
    Remove-Item Env:SD_UPD4_FIXTURE_RECEIPT -ErrorAction SilentlyContinue
    foreach ($path in @($stagingBase,$installBase,$agentBase,$lab)) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force } }
}

foreach ($path in @($stagingBase,$installBase,$agentBase,$lab)) { if (Test-Path -LiteralPath $path) { throw "Owned fixture path survived cleanup: $path" } }
foreach ($thumb in $certificates) {
    foreach ($store in @('Cert:\LocalMachine\Root','Cert:\CurrentUser\My')) {
        if (Test-Path -LiteralPath (Join-Path $store $thumb)) { throw 'Test certificate survived cleanup.' }
    }
}
[GC]::Collect(); [GC]::WaitForPendingFinalizers()
foreach ($name in $createdServices) { if (Get-Service -Name $name -ErrorAction SilentlyContinue) { throw "Test service survived cleanup: $name" } }
$record=Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
$record.cleanup='verified: exact machine public certificate and current-user signing key, owned synthetic services, staging/install prefixes and binaries removed'
[IO.File]::WriteAllText($receipt,($record | ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
Write-Host "WINDOWS FLEET PLATFORM FIXTURE PASSED; sanitized receipt: $receipt"
