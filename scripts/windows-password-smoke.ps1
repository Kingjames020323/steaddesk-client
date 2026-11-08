# Exercise the installed CLI on the isolated, disposable Windows runner.
param([Parameter(Mandatory)][string]$Package)
$ErrorActionPreference = 'Stop'
$installed = Join-Path $env:ProgramFiles 'SteadDesk\SteadDesk.exe'
Start-Process -FilePath $Package -ArgumentList '--silent-install'
$deadline = [DateTime]::UtcNow.AddMinutes(2)
do {
    $service = Get-Service -Name SteadDesk -ErrorAction SilentlyContinue
    if ($service.Status -eq 'Running' -and (Test-Path -LiteralPath $installed)) { break }
    Start-Sleep -Seconds 1
} while ([DateTime]::UtcNow -lt $deadline)
if ($service.Status -ne 'Running' -or !(Test-Path -LiteralPath $installed)) {
    throw 'Timed out waiting for the installed service'
}

$start = [Diagnostics.ProcessStartInfo]::new($installed)
$start.UseShellExecute = $false
$start.RedirectStandardInput = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.ArgumentList.Add('--password-stdin')
$secret = [byte[]]::new(32)
for ($i = 0; $i -lt $secret.Length; $i++) {
    $secret[$i] = [Security.Cryptography.RandomNumberGenerator]::GetInt32(33,127)
}
$child = [Diagnostics.Process]::Start($start)
try {
    $stdout = $child.StandardOutput.ReadToEndAsync()
    $stderr = $child.StandardError.ReadToEndAsync()
    $snap = Get-CimInstance Win32_Process -Filter "ProcessId=$($child.Id)"
    # Check the entire command line. Report it canonically only after validation.
    $expected = '^"?' + [regex]::Escape($installed) + '"?\s+--password-stdin\s*$'
    if ($snap.ExecutablePath -ne $installed -or $snap.CommandLine -notmatch $expected) {
        throw 'Installed CLI command line differs from executable plus stdin switch'
    }
    Write-Output 'WMI Win32_Process: SteadDesk.exe --password-stdin (only argument)'
    $pipe = $child.StandardInput.BaseStream
    $pipe.Write($secret, 0, $secret.Length)
    $pipe.WriteByte(10)
    $pipe.Flush()
    $child.StandardInput.Close()
    if (!$child.WaitForExit(30000)) { throw 'Password command timed out' }
    if ($child.ExitCode -ne 0 -or $stdout.Result -notmatch '(?m)^Done!\r?$') {
        throw 'The installed service did not acknowledge the new password'
    }
    Write-Output 'PASS: installed service acknowledged the stdin password'
} finally {
    [Array]::Clear($secret, 0, $secret.Length)
    if (!$child.HasExited) { $child.Kill() }
    $child.Dispose()
}
