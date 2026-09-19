param(
  [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$Host125Id,
  [string]$Host113Id,
  [string]$CoordinatorShadowEndpoint
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$releaseRoot = Join-Path $ProjectRoot 'releases\portable_host\candidate\0.2.1'
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $csc)) { throw "C# compiler unavailable: $csc" }
$source = Join-Path $ProjectRoot 'tray\BigQMTHostAgentTray.cs'
$modules = '__init__.py','coordinator_outbox.py','coordinator_fact_auth.py','host_fact_identity.py','host_fact_uploader.py','host_agent_account_policy.py','execution_lease_guard.py'
$Host125Id = ([string]$Host125Id).Trim()
$Host113Id = ([string]$Host113Id).Trim()
$CoordinatorShadowEndpoint = ([string]$CoordinatorShadowEndpoint).Trim()
if ([string]::IsNullOrWhiteSpace($Host125Id) -or [string]::IsNullOrWhiteSpace($Host113Id) -or [string]::IsNullOrWhiteSpace($CoordinatorShadowEndpoint)) {
  throw 'Host125Id, Host113Id and CoordinatorShadowEndpoint are required; refusing historical test-net placeholders.'
}
if ($Host125Id -match '^(192\.0\.2\.|198\.51\.100\.)' -or $Host113Id -match '^(192\.0\.2\.|198\.51\.100\.)' -or $CoordinatorShadowEndpoint -match '192\.0\.2\.') {
  throw 'Test-net placeholder host or endpoint is not allowed in a portable bundle.'
}
if ($CoordinatorShadowEndpoint -notmatch ':18666/api/v1/facts/ingest$') {
  throw 'CoordinatorShadowEndpoint must be the facts-only Shadow 18666 endpoint.'
}

foreach ($machine in @(
  @{ Name='BigQMT_Host_125'; HostId=$Host125Id; KeyId='host-125-fact-shadow-20260917' },
  @{ Name='BigQMT_Host_113'; HostId=$Host113Id; KeyId='host-113-fact-shadow-20260917' }
)) {
  $bundle = Join-Path $releaseRoot $machine.Name
  New-Item -ItemType Directory -Force -Path $bundle, (Join-Path $bundle 'scripts\host_agent'), (Join-Path $bundle 'scripts\coordinator'), (Join-Path $bundle 'src\kitling_bigqmt'), (Join-Path $bundle 'state\simulation'), (Join-Path $bundle 'logs') | Out-Null
  Copy-Item (Join-Path $ProjectRoot 'deploy\portable-host\provision_and_start.ps1') (Join-Path $bundle 'provision_and_start.ps1') -Force
  Copy-Item (Join-Path $ProjectRoot 'deploy\portable-host\start_host_tray.cmd') (Join-Path $bundle 'start_host_tray.cmd') -Force
  Copy-Item (Join-Path $ProjectRoot 'deploy\portable-host\README.md') (Join-Path $bundle 'README.md') -Force
  Copy-Item (Join-Path $ProjectRoot 'scripts\host_agent\collect_runtime_fact.py') (Join-Path $bundle 'scripts\host_agent\collect_runtime_fact.py') -Force
  Copy-Item (Join-Path $ProjectRoot 'scripts\host_agent\deliver_fact_outbox.py') (Join-Path $bundle 'scripts\host_agent\deliver_fact_outbox.py') -Force
  Copy-Item (Join-Path $ProjectRoot 'scripts\coordinator\manage_fact_identity.py') (Join-Path $bundle 'scripts\coordinator\manage_fact_identity.py') -Force
  foreach ($module in $modules) { Copy-Item (Join-Path $ProjectRoot ('src\kitling_bigqmt\' + $module)) (Join-Path $bundle ('src\kitling_bigqmt\' + $module)) -Force }
  $config = [ordered]@{
    schema_version = 1
    host_id = $machine.HostId
    fact_key_id = $machine.KeyId
    profile = 'simulation'
    audit_path = '../runtime_data/audit/simulation/native_tray.jsonl'
    outbox_path = 'state/simulation/host_agent_outbox.sqlite3'
    fact_secret_path = ('C:/ProgramData/Kitling/BigQMT/host-facts/' + $machine.KeyId + '.json')
    coordinator_endpoint = $CoordinatorShadowEndpoint
    interval_seconds = 300
    orders_enabled = $false
  }
  [IO.File]::WriteAllText((Join-Path $bundle 'machine.local.json'), ($config | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
  $compileArgs = @(
    '/nologo', '/target:winexe', '/optimize+',
    '/reference:System.dll', '/reference:System.Drawing.dll', '/reference:System.Windows.Forms.dll', '/reference:System.Web.Extensions.dll',
    ('/out:' + (Join-Path $bundle 'BigQMT_HostTray.exe')), $source
  )
  & $csc @compileArgs
  if ($LASTEXITCODE -ne 0) { throw "compile failed: $($machine.Name)" }
  $lines = Get-ChildItem -LiteralPath $bundle -Recurse -File | Where-Object { $_.Name -ne 'checksums.sha256' } | Sort-Object FullName | ForEach-Object {
    $relative = $_.FullName.Substring($bundle.Length + 1).Replace('\','/')
    "{0}  {1}" -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash, $relative
  }
  [IO.File]::WriteAllLines((Join-Path $bundle 'checksums.sha256'), $lines, (New-Object Text.UTF8Encoding($false)))
}
Write-Output "portable host bundles built: $releaseRoot"
