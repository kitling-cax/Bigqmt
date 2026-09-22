<#[
Apply one verified BigQMT package candidate to simulation and production QMT.

The script always creates a complete, timestamped package backup before
overlaying files and never starts QMT, Redis or a strategy.  Supply the QMT
Python roots explicitly so the same command works on .105, .125 and .113.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CandidatePackage,
    [Parameter(Mandatory = $true)]
    [string]$SimulationPythonDir,
    [Parameter(Mandatory = $true)]
    [string]$ProductionPythonDir,
    [string]$BackupRoot = (Join-Path $PSScriptRoot "..\..\..\backups\bridge"),
    [switch]$ConfirmDeploy
)

$ErrorActionPreference = "Stop"
if (-not $ConfirmDeploy) {
    throw "Refusing to deploy without -ConfirmDeploy. This command copies files into both QMT Python directories."
}

$candidate = (Resolve-Path -LiteralPath $CandidatePackage).Path
foreach ($required in @("version.py", "adapter_factory.py", "redis_rpc.py", "execution_admission.py", "adapters\order_guarded.py")) {
    if (-not (Test-Path -LiteralPath (Join-Path $candidate $required))) {
        throw "Candidate is missing required protected file: $required"
    }
}

$versionLine = Select-String -LiteralPath (Join-Path $candidate "version.py") -Pattern '^__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionLine) { throw "Candidate version.py has no __version__" }
$version = $versionLine.Matches[0].Groups[1].Value
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupBase = Join-Path ((Resolve-Path -LiteralPath $BackupRoot).Path) ("{0}_xtquant_big_convert_{1}" -f $stamp, $version)

$targets = @(
    @{ Profile = "simulation"; PythonDir = $SimulationPythonDir },
    @{ Profile = "production"; PythonDir = $ProductionPythonDir }
)
foreach ($target in $targets) {
    $pythonDir = (Resolve-Path -LiteralPath $target.PythonDir).Path
    $installed = Join-Path $pythonDir "bigqmt_signal_trader"
    if (-not (Test-Path -LiteralPath $installed)) {
        throw "Target bridge package does not exist: $installed"
    }
    $backup = Join-Path $backupBase $target.Profile
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Copy-Item -LiteralPath $installed -Destination (Join-Path $backup "bigqmt_signal_trader") -Recurse -Force
    Copy-Item -Path (Join-Path $candidate "*") -Destination $installed -Recurse -Force

    $installedVersion = Select-String -LiteralPath (Join-Path $installed "version.py") -Pattern '^__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
    if (-not $installedVersion -or $installedVersion.Matches[0].Groups[1].Value -ne $version) {
        throw "Post-copy version verification failed for $($target.Profile)"
    }
    Write-Output ("{0}: upgraded to {1}; backup={2}" -f $target.Profile, $version, $backup)
}
Write-Output "No QMT, Redis or BIGQMT_BRIDGE process was started or restarted."
