<#
Deploy only the empty, read-only Host Agent intent-preview endpoint to .121.
No credentials are stored by this script. SSH/SCP prompt interactively.
#>
[CmdletBinding()]
param(
    [string]$RemoteHost = "kitling@192.0.2.121",
    [string]$RemoteRoot = "/opt/bigqmt-coordinator/current",
    [string]$ServiceName = "kitling-bigqmt-coordinator.service",
    [string]$CoordinatorHealthUrl = "http://192.0.2.121:18443/healthz"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $projectRoot "scripts\coordinator\serve.py"
if (-not (Test-Path -LiteralPath $source)) { throw "missing local Coordinator source: $source" }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$remoteTemp = "/tmp/bigqmt_serve_$stamp.py"
$remoteBackup = "/opt/bigqmt-coordinator/backups/${stamp}_before_readonly_intent_preview"

Write-Host "[1/3] Uploading one Coordinator source file; SSH may ask for the .121 password."
& scp -- $source "${RemoteHost}:$remoteTemp"
if ($LASTEXITCODE -ne 0) { throw "SCP upload failed" }

Write-Host "[2/3] Backing up, replacing, and restarting only $ServiceName; sudo may ask for the remote password."
$remoteCommand = @"
set -eu
sudo mkdir -p '$remoteBackup'
sudo cp '$RemoteRoot/scripts/coordinator/serve.py' '$remoteBackup/serve.py'
sudo install -m 0644 '$remoteTemp' '$RemoteRoot/scripts/coordinator/serve.py'
rm -f '$remoteTemp'
sudo systemctl restart '$ServiceName'
systemctl is-active '$ServiceName'
curl --fail --silent --show-error '$CoordinatorHealthUrl'
"@
& ssh -tt -- $RemoteHost $remoteCommand
if ($LASTEXITCODE -ne 0) { throw "remote deployment or health check failed; backup remains at $remoteBackup" }

Write-Host "[3/3] Deployment completed. Run the local probe next:"
Write-Host "py -3.12 scripts\probe_host_agent_intent_preview.py --endpoint http://192.0.2.121:18443 --host-id 192.0.2.105"
