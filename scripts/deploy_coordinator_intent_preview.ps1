<#
Deploy only read-only Coordinator projections to .121 (intent preview and
strategy candidate catalog).
No credentials are stored by this script. SSH/SCP prompt interactively.
#>
[CmdletBinding()]
param(
    [string]$RemoteHost = "kitling@192.0.2.121",
    [string]$RemoteRoot = "/opt/bigqmt-coordinator/current",
    [string]$RemoteBackupRoot = "/opt/bigqmt-coordinator/backups",
    [string]$ServiceName = "kitling-bigqmt-coordinator.service",
    [string]$CoordinatorHealthUrl = "http://192.0.2.121:18443/healthz"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$sources = @(
    @{ Local = (Join-Path $projectRoot "scripts\coordinator\serve.py"); Remote = "scripts/coordinator/serve.py" },
    @{ Local = (Join-Path $projectRoot "src\kitling_bigqmt\strategy_catalog.py"); Remote = "src/kitling_bigqmt/strategy_catalog.py" }
)
foreach ($item in $sources) { if (-not (Test-Path -LiteralPath $item.Local)) { throw "missing local Coordinator source: $($item.Local)" } }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$remoteTempRoot = "/tmp/bigqmt_readonly_projection_$stamp"
$remoteBackup = "$RemoteBackupRoot/${stamp}_before_readonly_intent_preview"

Write-Host "[1/3] Uploading read-only Coordinator sources; SSH may ask for the .121 password."
& ssh -- $RemoteHost "mkdir -p '$remoteTempRoot/scripts/coordinator' '$remoteTempRoot/src/kitling_bigqmt'"
if ($LASTEXITCODE -ne 0) { throw "remote temp directory creation failed" }
foreach ($item in $sources) {
    $remoteTemp = "$remoteTempRoot/$($item.Remote)"
    & scp -- $item.Local "${RemoteHost}:$remoteTemp"
    if ($LASTEXITCODE -ne 0) { throw "SCP upload failed: $($item.Local)" }
}

Write-Host "[2/3] Backing up, replacing, and restarting only $ServiceName; sudo may ask for the remote password."
$remoteCommand = @"
set -eu
sudo mkdir -p '$remoteBackup'
sudo cp '$RemoteRoot/scripts/coordinator/serve.py' '$remoteBackup/serve.py'
if [ -f '$RemoteRoot/src/kitling_bigqmt/strategy_catalog.py' ]; then sudo cp '$RemoteRoot/src/kitling_bigqmt/strategy_catalog.py' '$remoteBackup/strategy_catalog.py'; fi
sudo install -m 0644 '$remoteTempRoot/scripts/coordinator/serve.py' '$RemoteRoot/scripts/coordinator/serve.py'
sudo install -m 0644 '$remoteTempRoot/src/kitling_bigqmt/strategy_catalog.py' '$RemoteRoot/src/kitling_bigqmt/strategy_catalog.py'
rm -rf '$remoteTempRoot'
sudo systemctl restart '$ServiceName'
systemctl is-active '$ServiceName'
curl --fail --silent --show-error '$CoordinatorHealthUrl'
"@
& ssh -tt -- $RemoteHost $remoteCommand
if ($LASTEXITCODE -ne 0) { throw "remote deployment or health check failed; backup remains at $remoteBackup" }

Write-Host "[3/3] Deployment completed. Run the local probe next:"
Write-Host "py -3.12 scripts\probe_host_agent_intent_preview.py --endpoint http://192.0.2.121:18443 --host-id 192.0.2.105"
