param([string]$PackageDir = 'package')
# Isolate the disposable runner before starting any package or service.
$ErrorActionPreference = 'Stop'
$names = 'relay.steaddesk.com','api.steaddesk.com'
$hostsFile = "$env:WINDIR\System32\drivers\etc\hosts"
foreach ($name in $names) {
  Add-Content -Path $hostsFile -Value "`n127.0.0.1 $name`n::1 $name" -Encoding ascii
}
Clear-DnsClientCache
foreach ($name in $names) {
  foreach ($ip in [Net.Dns]::GetHostAddresses($name)) {
    if (![Net.IPAddress]::IsLoopback($ip)) { throw 'Service name is not isolated' }
  }
}
$releaseVersion = (Get-Content -LiteralPath "$PSScriptRoot/../RELEASE_VERSION" -Raw).Trim()
$product = if ($env:STEADDESK_EDITION -eq 'support') { 'SteadDesk Support' } else { 'SteadDesk' }
$prefix = $product.Replace(' ', '')
$package = (Resolve-Path "$PackageDir/$prefix-$releaseVersion-x64.exe").Path
$resource = (Get-Item -LiteralPath $package).VersionInfo
if ($resource.FileVersion -cne $releaseVersion -or $resource.ProductVersion -cne $releaseVersion) { throw 'Unexpected package version resource' }
if ((Get-AuthenticodeSignature -LiteralPath $package).Status -ne 'NotSigned') { throw 'Expected an unsigned EXE' }
$expected = ((Get-Content (Join-Path $PackageDir SHA256SUMS)) -split '\s+')[0]
if ((Get-FileHash $package).Hash -ne $expected) { throw 'Package checksum mismatch' }
if ((Get-Item $package).VersionInfo.ProductName -cne $product) { throw 'Unexpected package ProductName' }
foreach ($binary in @($package, "$env:LOCALAPPDATA\rustdesk\rustdesk.exe", "$env:LOCALAPPDATA\rustdesk\SteadDesk.exe", "$env:LOCALAPPDATA\$product\$product.exe", "$env:ProgramFiles\$product\$product.exe", "$env:ProgramFiles\$product\rustdesk.exe")) {
  New-NetFirewallRule -DisplayName "Offline UI $binary" -Program $binary -Direction Outbound -Action Block | Out-Null
}
