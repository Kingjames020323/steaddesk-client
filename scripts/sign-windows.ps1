#Requires -Version 7
<#
.SYNOPSIS
Sign the Windows executable in a checked release bundle using a local RSA PFX.
.EXAMPLE
.\scripts\sign-windows.ps1 -ReleaseDir .\unsigned -OutputDir .\windows-signed -PfxPath E:\release.pfx
.NOTES
Requires PowerShell 7, Python 3.10+, and Windows SDK
10.0.22000+ SignTool on PATH. The signing host needs the publisher's trust
chain and access to the selected RFC 3161 timestamp authority.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ReleaseDir,
    [Parameter(Mandatory)][string]$OutputDir,
    [Parameter(Mandatory)][string]$PfxPath,
    [uri]$TimestampUrl = 'http://timestamp.digicert.com'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($TimestampUrl.Scheme -notin @('https', 'http')) { throw 'Use an HTTP(S) RFC 3161 timestamp URL.' }
$signTool = (Get-Command 'signtool.exe' -CommandType Application).Source
$python = Get-Command 'py.exe' -CommandType Application -ErrorAction SilentlyContinue
$pythonArgs = @('-3')
if (-not $python) {
    $python = Get-Command 'python.exe' -CommandType Application
    $pythonArgs = @()
}
$pythonExe = $python.Source
$helper = Join-Path $PSScriptRoot 'signing_bundle.py'
$source = (Resolve-Path -LiteralPath $ReleaseDir).ProviderPath
$pfx = (Resolve-Path -LiteralPath $PfxPath).ProviderPath
$output = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory.' }
$scratch = Join-Path (Split-Path -Parent $output) ('.steaddesk-sign-' + [Guid]::NewGuid())
$null = New-Item -Type Directory -Path $scratch

function Invoke-SignTool([string[]]$ToolArgs) {
    & $signTool @ToolArgs
    if ($LASTEXITCODE -ne 0) { throw "SignTool $($ToolArgs[0]) returned $LASTEXITCODE." }
}

$password = $null
$certificate = $null
$rsa = $null
try {
    $unsigned = & $pythonExe @pythonArgs $helper prepare windows $source $scratch
    if ($LASTEXITCODE -ne 0) { throw 'Release bundle preflight failed.' }
    $signed = Join-Path $scratch ($unsigned -replace '\.unsigned\.exe$', '.exe')
    Copy-Item -LiteralPath (Join-Path (Join-Path $scratch 'bundle') $unsigned) -Destination $signed

    # SignTool prepares/ingests the digest. Only this PowerShell process sees the private key.
    $password = Read-Host 'PFX password' -AsSecureString
    $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
        $pfx, $password, [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet)
    $rsa = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($certificate)
    if (-not $rsa) { throw 'Provide a code-signing PFX with an RSA private key.' }
    $publicCert = Join-Path $scratch 'publisher.cer'
    [IO.File]::WriteAllBytes($publicCert, $certificate.Export(
        [System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
    Invoke-SignTool @('sign', '/dg', $scratch, '/fd', 'SHA256', '/f', $publicCert, $signed)
    $digest = [Convert]::FromBase64String([IO.File]::ReadAllText("$signed.dig"))
    $signature = $rsa.SignHash($digest, [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
    [IO.File]::WriteAllText("$signed.dig.signed", [Convert]::ToBase64String($signature), [Text.Encoding]::ASCII)

    # /di consumes the SHA-256 digest above. Windows 11 SDK rejects /fd on ingestion.
    Invoke-SignTool @('sign', '/fdws', '/di', $scratch, $signed)
    Invoke-SignTool @('timestamp', '/tr', $TimestampUrl.AbsoluteUri, '/td', 'SHA256', $signed)
    Invoke-SignTool @('verify', '/pa', '/all', '/tw', '/v', $signed)
    $verified = Get-AuthenticodeSignature -LiteralPath $signed
    if ($verified.SignerCertificate.Thumbprint -ne $certificate.Thumbprint -or -not $verified.TimeStamperCertificate) {
        throw 'Publisher identity or timestamp verification failed.'
    }
    & $pythonExe @pythonArgs $helper publish windows $scratch $output
    if ($LASTEXITCODE -ne 0) { throw 'Publishing the checked bundle failed.' }
    Write-Output "Windows signature verified. Release bundle written to $output"
}
finally {
    if ($rsa) { $rsa.Dispose() }
    if ($certificate) { $certificate.Dispose() }
    if ($password) { $password.Dispose() }
    Remove-Item -LiteralPath $scratch -Recurse -Force
}
