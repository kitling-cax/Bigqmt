param(
  [string]$Root = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)
$configPath = Join-Path $Root 'machine.local.json'
if (-not (Test-Path -LiteralPath $configPath)) { throw "missing machine.local.json: $configPath" }
$cfg = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($key in 'host_id','profile','audit_path','outbox_path','fact_secret_path','coordinator_endpoint') {
  if ([string]::IsNullOrWhiteSpace([string]$cfg.$key)) { throw "machine.local.json missing $key" }
}
if ([string]$cfg.coordinator_endpoint -notmatch ':18666/api/v1/facts/ingest$') { throw 'only Shadow 18666 facts endpoint is allowed' }
function Resolve-BundlePath([string]$Value) {
  if ([IO.Path]::IsPathRooted($Value)) { return [IO.Path]::GetFullPath($Value) }
  return [IO.Path]::GetFullPath((Join-Path $Root $Value))
}
& py -3.12 --version
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required' }
$auditPath = Resolve-BundlePath ([string]$cfg.audit_path)
$outboxPath = Resolve-BundlePath ([string]$cfg.outbox_path)
$secretPath = Resolve-BundlePath ([string]$cfg.fact_secret_path)

$secretDir = Split-Path -Parent $secretPath
New-Item -ItemType Directory -Force -Path $secretDir, (Split-Path -Parent $outboxPath), (Join-Path $Root 'logs') | Out-Null
if (-not (Test-Path -LiteralPath $secretPath)) {
  $keyId = if ([string]::IsNullOrWhiteSpace([string]$cfg.fact_key_id)) { "host-$($cfg.host_id)-fact-shadow" -replace '[^A-Za-z0-9_-]','-' } else { [string]$cfg.fact_key_id }
  & py -3.12 (Join-Path $Root 'scripts\coordinator\manage_fact_identity.py') --host-id ([string]$cfg.host_id) --key-id $keyId --output $secretPath
  if ($LASTEXITCODE -ne 0) { throw 'Fact Secret generation failed' }
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls $secretDir /inheritance:r /grant:r 'SYSTEM:(F)' 'BUILTIN\Administrators:(F)' "$identity:(F)" | Out-Null
& icacls $secretPath /inheritance:r /grant:r 'SYSTEM:(F)' 'BUILTIN\Administrators:(F)' "$identity:(F)" | Out-Null

if (-not (Test-Path -LiteralPath $auditPath)) {
  Start-Process -FilePath (Join-Path $Root 'BigQMT_HostTray.exe') -WorkingDirectory $Root
  Write-Warning "Host tray started in waiting state; native tray audit is not available yet: $auditPath"
  return
}

$collect = @('--profile',[string]$cfg.profile,'--host-id',[string]$cfg.host_id,'--audit-path',$auditPath,'--outbox-path',$outboxPath)
& py -3.12 (Join-Path $Root 'scripts\host_agent\collect_runtime_fact.py') @collect
if ($LASTEXITCODE -ne 0) { throw 'local fact collection failed' }
$deliver = @('--profile',[string]$cfg.profile,'--secret-file',$secretPath,'--outbox-path',$outboxPath,'--endpoint',[string]$cfg.coordinator_endpoint)
& py -3.12 (Join-Path $Root 'scripts\host_agent\deliver_fact_outbox.py') @deliver
$deliveryExit = $LASTEXITCODE
Start-Process -FilePath (Join-Path $Root 'BigQMT_HostTray.exe') -WorkingDirectory $Root
if ($deliveryExit -ne 0) { Write-Warning 'Host tray started; first delivery remains pending for retry.' }
