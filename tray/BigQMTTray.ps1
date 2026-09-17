param(
  [ValidateSet('simulation','production_readonly')]
  [string]$Profile = 'simulation',
  [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$PythonPath = "py",
  [int]$DashboardPort = 0,
  [int]$ShadowCycleHour = 15,
  [int]$ShadowCycleMinute = 35,
  [int]$LakeCycleHour = 16,
  [int]$LakeCycleMinute = 10,
  [int]$DailyRecordHour = 16,
  [int]$DailyRecordMinute = 20,
  [int]$ExecutionCycleHour = 9,
  [int]$ExecutionCycleMinute = 35
)

$bootstrapProjectRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\','/')
$bootstrapAuditDir = Join-Path $bootstrapProjectRoot ("runtime_data\audit\" + $Profile)
$bootstrapFailurePath = Join-Path $bootstrapAuditDir 'tray_bootstrap_errors.log'
trap {
  try {
    New-Item -ItemType Directory -Force -Path $bootstrapAuditDir | Out-Null
    $line = (Get-Date).ToUniversalTime().ToString('o') + ' | ' + $_.Exception.GetType().FullName + ' | ' + $_.Exception.Message
    Add-Content -LiteralPath $bootstrapFailurePath -Value $line -Encoding UTF8
  } catch { }
  exit 2
}

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# NotifyIcon is a Windows shell UI object.  Running it from an MTA PowerShell
# host can leave a live process with no notification-area icon.  Every bundled
# launcher now uses -STA; retain this explicit guard so a misconfigured copied
# deployment fails immediately instead of pretending to run.
if ([Threading.Thread]::CurrentThread.ApartmentState -ne [Threading.ApartmentState]::STA) {
  throw 'BigQMT Tray requires an STA PowerShell host. Launch with powershell.exe -STA.'
}

$ProjectRoot = $bootstrapProjectRoot
$profileLabel = if ($Profile -eq 'simulation') { 'SIMULATION' } else { 'PRODUCTION_READONLY' }
$dashboardRoute = if ($Profile -eq 'simulation') { '/simulation/overview' } else { '/production-readonly/overview' }
$DashboardPort = if ($DashboardPort -gt 0) { $DashboardPort } elseif ($Profile -eq 'simulation') { 17890 } else { 17891 }
$hashBytes = [Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($ProjectRoot.ToLowerInvariant() + '|' + $Profile))
$trayName = "Local\BigQMTTray-" + ([BitConverter]::ToString($hashBytes).Replace('-','').Substring(0,16))
$created = $false
$mutex = New-Object Threading.Mutex($true, $trayName, [ref]$created)
if (-not $created) {
  try {
    New-Item -ItemType Directory -Force -Path $bootstrapAuditDir | Out-Null
    $record = [ordered]@{ event_time = (Get-Date).ToUniversalTime().ToString('o'); profile = $Profile; event = 'tray_duplicate_instance_detected'; detail = 'another instance owns the profile mutex'; orders_enabled = $false; execution_consumer_enabled = $false }
    ($record | ConvertTo-Json -Compress) | Add-Content -LiteralPath (Join-Path $bootstrapAuditDir 'tray_events.jsonl') -Encoding UTF8
  } catch { }
  exit 0
}
$auditDir = Join-Path $ProjectRoot ("runtime_data\audit\" + $Profile)
$auditPath = Join-Path $auditDir 'tray_events.jsonl'
$redisConfigName = if ($Profile -eq 'simulation') { 'redis-simulation.conf' } else { 'redis-production.conf' }
$redisConfigPath = Join-Path $ProjectRoot ("config\redis\" + $redisConfigName)
$redisExecutable = Join-Path $ProjectRoot 'runtime_data\redis\_package_inspect\Redis-8.10.1-Windows-x64-msys2\redis-server.exe'
$redisPort = if ($Profile -eq 'simulation') { 6379 } else { 6380 }
$strategyRuntimePolicyPath = Join-Path $ProjectRoot 'config\strategy_runtime_policy.json'
$script:lastHealth = ''
$script:lastLakeDate = ''
$script:lastShadowDate = ''
$script:lastDailyRecordDate = ''
$script:lastExecutionCycleDate = ''
$script:lastAccountSnapshotHour = ''
$script:nextAccountSnapshotAttemptAt = [datetime]::MinValue
$script:nextLakeAttemptAt = [datetime]::MinValue
$script:nextShadowAttemptAt = [datetime]::MinValue
$script:nextExecutionCycleAttemptAt = [datetime]::MinValue
$script:nextQmtStartAttemptAt = [datetime]::MinValue
$script:nextBridgeProbeAt = [datetime]::MinValue
$script:lastBridgeProbe = @{ status = 'PENDING'; detail = 'not yet probed'; checked_at = [datetime]::MinValue }
$windowsRunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$windowsStartupValueName = if ($Profile -eq 'simulation') { 'BigQMTTray-Simulation' } else { 'BigQMTTray-ProductionReadonly' }

function Write-TrayEvent([string]$EventName, [string]$Detail = '') {
  try {
    New-Item -ItemType Directory -Force -Path $auditDir | Out-Null
    $record = [ordered]@{
      event_time = (Get-Date).ToUniversalTime().ToString('o')
      profile = $Profile
      event = $EventName
      detail = $Detail
      orders_enabled = $false
      execution_consumer_enabled = $false
    }
    ($record | ConvertTo-Json -Compress) | Add-Content -LiteralPath $auditPath -Encoding UTF8
  } catch {
    # Audit failure must not turn into a retry loop or an order capability.
  }
}
Write-TrayEvent 'tray_started' 'read-only operator process started'

function Get-WindowsStartupCommand {
  try {
    # Get-ItemPropertyValue emits a provider warning every timer tick when the
    # optional Run value is absent.  Inspect the property object instead so
    # the normal "startup disabled" state is quiet and cannot obscure tray
    # diagnostics.
    $item = Get-ItemProperty -LiteralPath $windowsRunKey -ErrorAction Stop
    $property = $item.PSObject.Properties[$windowsStartupValueName]
    if ($null -eq $property) { return '' }
    return [string]$property.Value
  } catch {
    return ''
  }
}
function Test-WindowsStartupEnabled {
  return -not [string]::IsNullOrWhiteSpace((Get-WindowsStartupCommand))
}
function Set-WindowsStartup([bool]$Enabled) {
  if ($Enabled) {
    # Run directly through PowerShell so Windows logon starts a hidden tray
    # process without a persistent command window.  The profile is explicit:
    # simulation and production-readonly can be enabled independently.
    $powershellExe = Join-Path $PSHOME 'powershell.exe'
    $command = '"' + $powershellExe + '" -STA -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $PSCommandPath + '" -Profile ' + $Profile + ' -ProjectRoot "' + $ProjectRoot + '"'
    New-Item -Path $windowsRunKey -Force | Out-Null
    New-ItemProperty -LiteralPath $windowsRunKey -Name $windowsStartupValueName -PropertyType String -Value $command -Force | Out-Null
    Write-TrayEvent 'windows_startup_enabled' ("registry_value=" + $windowsStartupValueName)
  } else {
    Remove-ItemProperty -LiteralPath $windowsRunKey -Name $windowsStartupValueName -ErrorAction SilentlyContinue
    Write-TrayEvent 'windows_startup_disabled' ("registry_value=" + $windowsStartupValueName)
  }
}

function Get-StrategyRuntimePolicy {
  $default = [ordered]@{
    schema_version = 1
    simulation = [ordered]@{ v1_1_15_auto_run_enabled = $false }
    production = [ordered]@{ strategy_recovery_enabled = $false }
  }
  try {
    if (-not (Test-Path -LiteralPath $strategyRuntimePolicyPath)) { return $default }
    $loaded = Get-Content -LiteralPath $strategyRuntimePolicyPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $loaded) { return $default }
    return $loaded
  } catch {
    Write-TrayEvent 'strategy_runtime_policy_read_error' $_.Exception.Message
    return $default
  }
}
function Test-SimulationStrategyRunEnabled {
  if ($Profile -ne 'simulation') { return $false }
  $policy = Get-StrategyRuntimePolicy
  return [bool]($policy.simulation.v1_1_15_auto_run_enabled)
}
function Set-SimulationStrategyRunEnabled([bool]$Enabled) {
  if ($Profile -ne 'simulation') { throw 'simulation strategy switch is unavailable in the formal profile' }
  $existing = Get-StrategyRuntimePolicy
  $formalRecoveryEnabled = [bool]($existing.production.strategy_recovery_enabled)
  $policy = [ordered]@{
    schema_version = 1
    simulation = [ordered]@{
      v1_1_15_auto_run_enabled = $Enabled
      policy_note = 'Tray-owned master switch. When false, strategy signal, account and daily-record sampling may continue, but no automatic or manual v1.1.15 order cycle may be submitted.'
    }
    production = [ordered]@{
      strategy_recovery_enabled = $formalRecoveryEnabled
      policy_note = 'Reserved for a future separately approved per-strategy formal execution admission. This flag grants no order capability.'
    }
  }
  $directory = Split-Path -Parent $strategyRuntimePolicyPath
  New-Item -ItemType Directory -Force -Path $directory | Out-Null
  $temporary = Join-Path $directory ('.strategy_runtime_policy.' + [Guid]::NewGuid().ToString('N') + '.tmp')
  try {
    [IO.File]::WriteAllText($temporary, ($policy | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $strategyRuntimePolicyPath -Force
    Write-TrayEvent $(if ($Enabled) { 'simulation_strategy_enabled' } else { 'simulation_strategy_disabled' }) 'strategy=S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15'
  } finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
  }
}
function Test-FormalStrategyRecoveryEnabled {
  if ($Profile -ne 'production_readonly') { return $false }
  $policy = Get-StrategyRuntimePolicy
  return [bool]($policy.production.strategy_recovery_enabled)
}
function Set-FormalStrategyRecoveryEnabled([bool]$Enabled) {
  if ($Profile -ne 'production_readonly') { throw 'formal strategy recovery switch is unavailable in the simulation profile' }
  # This is deliberately only a recovery-intent switch.  It cannot alter the
  # separate production Bridge order lock or admit a strategy by itself.
  $existing = Get-StrategyRuntimePolicy
  $simulationEnabled = [bool]($existing.simulation.v1_1_15_auto_run_enabled)
  $policy = [ordered]@{
    schema_version = 1
    simulation = [ordered]@{
      v1_1_15_auto_run_enabled = $simulationEnabled
      policy_note = 'Tray-owned master switch. When false, strategy signal, account and daily-record sampling may continue, but no automatic or manual v1.1.15 order cycle may be submitted.'
    }
    production = [ordered]@{
      strategy_recovery_enabled = $Enabled
      policy_note = 'Recovery-intent only. Formal execution remains locked until a separate per-strategy admission and all runtime gates pass.'
    }
  }
  $directory = Split-Path -Parent $strategyRuntimePolicyPath
  New-Item -ItemType Directory -Force -Path $directory | Out-Null
  $temporary = Join-Path $directory ('.strategy_runtime_policy.' + [Guid]::NewGuid().ToString('N') + '.tmp')
  try {
    [IO.File]::WriteAllText($temporary, ($policy | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporary -Destination $strategyRuntimePolicyPath -Force
    Write-TrayEvent $(if ($Enabled) { 'formal_strategy_recovery_intent_enabled' } else { 'formal_strategy_recovery_intent_disabled' }) 'orders remain locked; no strategy admitted by this setting alone'
  } finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
  }
}

function Invoke-Project([string[]]$ProjectArgs) {
  & $PythonPath (Join-Path $ProjectRoot 'scripts\bigqmt_runtime.py') @ProjectArgs '--profile' $Profile 2>$null | ConvertFrom-Json
}
function Invoke-QmtLauncher([string[]]$LauncherArgs) {
  & $PythonPath (Join-Path $ProjectRoot 'scripts\qmt_launcher_cli.py') @LauncherArgs '--profile' $Profile 2>$null | ConvertFrom-Json
}
function Test-LocalTcpPort([int]$Port) {
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $task = $client.ConnectAsync('127.0.0.1', $Port)
    return $task.Wait(500) -and $client.Connected
  } catch { return $false } finally { $client.Dispose() }
}
function ConvertTo-MsysPath([string]$WindowsPath) {
  if ($WindowsPath -notmatch '^([A-Za-z]):[\\/](.*)$') { throw "cannot convert non-drive path to MSYS path: $WindowsPath" }
  return '/cygdrive/' + $matches[1].ToLowerInvariant() + '/' + ($matches[2] -replace '\\','/')
}
function Ensure-Redis {
  # Only start a missing profile-local Redis listener. It never kills a
  # process, restarts QMT, writes to an account, or changes the order lock.
  if (Test-LocalTcpPort $redisPort) { return $true }
  if (-not (Test-Path -LiteralPath $redisExecutable) -or -not (Test-Path -LiteralPath $redisConfigPath)) {
    Write-TrayEvent 'redis_start_blocked' "missing executable or config for port $redisPort"
    return $false
  }
  try {
    Start-Process -FilePath $redisExecutable -ArgumentList @(ConvertTo-MsysPath $redisConfigPath) -WindowStyle Hidden
    Start-Sleep -Milliseconds 750
    $online = Test-LocalTcpPort $redisPort
    Write-TrayEvent $(if ($online) { 'redis_started' } else { 'redis_start_failed' }) ("port=" + $redisPort + "; config=" + $redisConfigName)
    return $online
  } catch {
    Write-TrayEvent 'redis_start_error' $_.Exception.Message
    return $false
  }
}
function Ensure-QmtStarted {
  # Starting a missing profile-local QMT is safe and idempotent.  We never
  # kill/restart a live QMT automatically: an unhealthy terminal may have a
  # visible broker warning or unresolved orders and needs an operator choice.
  try {
    $status = Invoke-QmtLauncher @('status')
    if (-not $status.ok) {
      Write-TrayEvent 'qmt_status_error' ([string]$status.error)
      return $status
    }
    if ($status.process_running) { return $status }
    if ((Get-Date) -lt $script:nextQmtStartAttemptAt) { return $status }
    $script:nextQmtStartAttemptAt = (Get-Date).AddMinutes(1)
    $started = Invoke-QmtLauncher @('open')
    Write-TrayEvent $(if ($started.ok) { 'qmt_start_requested' } else { 'qmt_start_failed' }) ("result=" + [string]$started.result + "; error=" + [string]$started.error)
    return $started
  } catch {
    Write-TrayEvent 'qmt_start_error' $_.Exception.Message
    return $null
  }
}
function Invoke-Health {
  & $PythonPath (Join-Path $ProjectRoot 'scripts\check_tray_health.py') '--profile' $Profile '--port' $DashboardPort 2>$null | ConvertFrom-Json
}
function Invoke-BridgeProbeIfDue {
  # A Bridge liveness signal must not be inferred from the shared FormulaServer
  # port or an old SQLite snapshot.  This queues exactly one allow-listed
  # read-only ``ping`` per minute; it never requests account data or sends an
  # order.  A failed probe only keeps the tray visibly fail-closed.
  $now = Get-Date
  if ($now -lt $script:nextBridgeProbeAt) { return $script:lastBridgeProbe }
  $script:nextBridgeProbeAt = $now.AddMinutes(1)
  try {
    $result = & $PythonPath (Join-Path $ProjectRoot 'scripts\check_bridge_ping.py') '--profile' $Profile '--timeout' '3' 2>$null | ConvertFrom-Json
    if ($null -eq $result) { throw 'Bridge probe returned no JSON' }
    $result | Add-Member -NotePropertyName checked_at -NotePropertyValue $now -Force
    $prior = [string]$script:lastBridgeProbe.status
    $script:lastBridgeProbe = $result
    if ($prior -ne [string]$result.status) { Write-TrayEvent 'bridge_live_changed' ("status=" + [string]$result.status + "; " + [string]$result.detail) }
  } catch {
    $script:lastBridgeProbe = @{ status = 'DEGRADED'; detail = $_.Exception.Message; checked_at = $now }
    Write-TrayEvent 'bridge_live_probe_error' $_.Exception.Message
  }
  return $script:lastBridgeProbe
}
function Invoke-LakeCycle {
  & $PythonPath (Join-Path $ProjectRoot 'scripts\run_lake_cycle.py') '--profile' $Profile 2>$null | ConvertFrom-Json
}
function Invoke-CloseShadow {
  if ($Profile -ne 'simulation') { throw 'v1.1.15 close shadow is simulation-only' }
  & $PythonPath (Join-Path $ProjectRoot 'scripts\run_v1_1_15_close_shadow.py') 2>$null | ConvertFrom-Json
}
function Invoke-DailyOperationsRecord {
  if ($Profile -ne 'simulation') { throw 'v1.1.15 daily operations record is simulation-only' }
  & $PythonPath (Join-Path $ProjectRoot 'scripts\record_v1_1_15_simulation_daily.py') 2>$null | ConvertFrom-Json
}
function Invoke-V1_1_15SimulationCycle([bool]$Execute = $false) {
  if ($Profile -ne 'simulation') { throw 'v1.1.15 execution cycle is simulation-only' }
  $args = @((Join-Path $ProjectRoot 'scripts\run_v1_1_15_simulation_cycle.py'))
  if ($Execute) { $args += '--execute' }
  & $PythonPath @args 2>$null | ConvertFrom-Json
}
function Invoke-V1_1_15SimulationCycleIfDue {
  # Tray is the sole simulation scheduler. It makes one bounded attempt per
  # QMT-confirmed trading day; the Python cycle still performs fresh account,
  # quote, open-order, attribution and reconciliation checks before it arms a
  # 120-second submit window. Production never reaches this function.
  if ($Profile -ne 'simulation') { return }
  # This persistent master switch is intentionally checked immediately before
  # scheduling.  Turning it off stops strategy submissions without stopping
  # QMT, Bridge, Redis, sampling, shadow signals, or the daily audit record.
  if (-not (Test-SimulationStrategyRunEnabled)) { return }
  $now = Get-Date
  if ($now.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)) { return }
  $today = $now.ToString('yyyy-MM-dd')
  if ($now.Hour -lt $ExecutionCycleHour -or ($now.Hour -eq $ExecutionCycleHour -and $now.Minute -lt $ExecutionCycleMinute)) { return }
  if ($now.Hour -gt 14 -or ($now.Hour -eq 14 -and $now.Minute -gt 50)) { return }
  if ($script:lastExecutionCycleDate -eq $today -or $now -lt $script:nextExecutionCycleAttemptAt) { return }
  try {
    $result = Invoke-V1_1_15SimulationCycle $true
    $status = [string]$result.status
    $detail = [string]$result.error
    if ($status -in @('SUBMITTED','ALIGNED_NO_ORDER','PREFLIGHT_PASSED_NO_ORDER')) {
      $script:lastExecutionCycleDate = $today
      $script:nextExecutionCycleAttemptAt = [datetime]::MinValue
      Write-TrayEvent 'v1_1_15_cycle_auto' ("status=" + $status + "; evidence=" + [string]$result.evidence + "; orders_enabled=false")
    } elseif ($detail -match 'timed out|timeout|connection|refused|Redis|RPC') {
      $script:nextExecutionCycleAttemptAt = $now.AddMinutes(10)
      Write-TrayEvent 'v1_1_15_cycle_auto_retryable_error' ("status=" + $status + "; retry_after=" + $script:nextExecutionCycleAttemptAt.ToString('o') + "; " + $detail)
    } else {
      # A risk/reconciliation/calendar/holding-period block is an intentional
      # fail-closed result, never a reason to keep attempting an order today.
      $script:lastExecutionCycleDate = $today
      $script:nextExecutionCycleAttemptAt = [datetime]::MinValue
      Write-TrayEvent 'v1_1_15_cycle_auto_blocked' ("status=" + $status + "; error=" + $detail + "; evidence=" + [string]$result.evidence + "; orders_enabled=false")
    }
  } catch {
    $script:nextExecutionCycleAttemptAt = $now.AddMinutes(10)
    Write-TrayEvent 'v1_1_15_cycle_auto_error' ("retry_after=" + $script:nextExecutionCycleAttemptAt.ToString('o') + "; " + $_.Exception.Message)
  }
}
function Invoke-DailyOperationsRecordIfDue {
  if ($Profile -ne 'simulation') { return }
  $now = Get-Date
  $today = $now.ToString('yyyy-MM-dd')
  if ($now.Hour -lt $DailyRecordHour -or ($now.Hour -eq $DailyRecordHour -and $now.Minute -lt $DailyRecordMinute)) { return }
  if ($script:lastDailyRecordDate -eq $today) { return }
  try {
    $result = Invoke-DailyOperationsRecord
    if ([string]$result.status -eq 'PASSED') {
      $script:lastDailyRecordDate = $today
      Write-TrayEvent 'v1_1_15_daily_operations_record_auto' ("status=PASSED; nav=" + [string]$result.nav + "; evidence=" + [string]$result.evidence)
    } else {
      Write-TrayEvent 'v1_1_15_daily_operations_record_blocked' ("status=" + [string]$result.status + "; evidence=" + [string]$result.evidence)
    }
  } catch {
    Write-TrayEvent 'v1_1_15_daily_operations_record_error' $_.Exception.Message
  }
}
function Invoke-HourlyAccountSnapshotIfDue {
  # v1.1.15 is daily. Keep durable account/position facts fresh once per
  # hour, with a short retry after a transient read-only RPC failure.
  $now = Get-Date
  if ($now -lt $script:nextAccountSnapshotAttemptAt) { return }
  $hour = $now.ToString('yyyy-MM-dd-HH')
  if ($script:lastAccountSnapshotHour -eq $hour) { return }
  $configName = if ($Profile -eq 'simulation') { 'host_gateway.simulation.json' } else { 'host_gateway.production_readonly.json' }
  try {
    $result = & $PythonPath (Join-Path $ProjectRoot 'scripts\run_readonly_snapshot.py') '--config' (Join-Path $ProjectRoot ('config\' + $configName)) 2>$null | ConvertFrom-Json
    if ([string]$result.status -eq 'PASSED') {
      $script:lastAccountSnapshotHour = $hour
      $script:nextAccountSnapshotAttemptAt = [datetime]::MinValue
      Write-TrayEvent 'hourly_account_snapshot' ('status=PASSED; run_id=' + [string]$result.run_id + '; positions=' + [string]$result.positions + '; orders=' + [string]$result.orders + '; trades=' + [string]$result.trades + '; broker_call_made=false')
    } else {
      $script:nextAccountSnapshotAttemptAt = $now.AddMinutes(10)
      Write-TrayEvent 'hourly_account_snapshot_blocked' ('status=' + [string]$result.status + '; retry_after=' + $script:nextAccountSnapshotAttemptAt.ToString('o'))
    }
  } catch {
    $script:nextAccountSnapshotAttemptAt = $now.AddMinutes(10)
    Write-TrayEvent 'hourly_account_snapshot_error' ('retry_after=' + $script:nextAccountSnapshotAttemptAt.ToString('o') + '; ' + $_.Exception.Message)
  }
}
function Invoke-CloseShadowIfDue {
  if ($Profile -ne 'simulation') { return }
  $now = Get-Date
  $today = $now.ToString('yyyy-MM-dd')
  if ($now.Hour -lt $ShadowCycleHour -or ($now.Hour -eq $ShadowCycleHour -and $now.Minute -lt $ShadowCycleMinute)) { return }
  if ($script:lastShadowDate -eq $today) { return }
  if ($now -lt $script:nextShadowAttemptAt) { return }
  try {
    $result = Invoke-CloseShadow
    $resultCode = [string]$result.result
    if ($resultCode -in @('RECORDED','DUPLICATE')) {
      $script:lastShadowDate = $today
      $script:nextShadowAttemptAt = [datetime]::MinValue
      Write-TrayEvent 'v1_1_15_close_shadow_auto' ("result=" + $resultCode + "; day=" + [string]$result.signal_day + "; target=" + [string]$result.desired_qmt + "; orders_enabled=false")
    } else {
      $script:nextShadowAttemptAt = $now.AddMinutes(10)
      Write-TrayEvent 'v1_1_15_close_shadow_auto_blocked' ("result=" + $resultCode + "; retry_after=" + $script:nextShadowAttemptAt.ToString('o') + "; orders_enabled=false")
    }
  } catch {
    $script:nextShadowAttemptAt = $now.AddMinutes(10)
    Write-TrayEvent 'v1_1_15_close_shadow_auto_error' ("retry_after=" + $script:nextShadowAttemptAt.ToString('o') + "; " + $_.Exception.Message)
  }
}
function Invoke-LakeCycleIfDue {
  if ($Profile -ne 'simulation') { return }
  $now = Get-Date
  $today = $now.ToString('yyyy-MM-dd')
  if ($now.Hour -lt $LakeCycleHour -or ($now.Hour -eq $LakeCycleHour -and $now.Minute -lt $LakeCycleMinute)) { return }
  if ($script:lastLakeDate -eq $today) { return }
  if ($now -lt $script:nextLakeAttemptAt) { return }
  try {
    $result = Invoke-LakeCycle
    if ([string]$result.status -eq 'PASSED') {
      $script:lastLakeDate = $today
      $script:nextLakeAttemptAt = [datetime]::MinValue
      Write-TrayEvent 'lake_cycle_auto' ("status=PASSED; export_returncode=" + [string]$result.export_returncode + "; evidence=" + [string]$result.evidence_path)
    } else {
      $script:nextLakeAttemptAt = $now.AddMinutes(10)
      Write-TrayEvent 'lake_cycle_auto_blocked' ("status=" + [string]$result.status + "; retry_after=" + $script:nextLakeAttemptAt.ToString('o'))
    }
  } catch {
    $script:nextLakeAttemptAt = $now.AddMinutes(10)
    Write-TrayEvent 'lake_cycle_auto_error' ("retry_after=" + $script:nextLakeAttemptAt.ToString('o') + "; " + $_.Exception.Message)
  }
}
function Dashboard-Online { try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 "http://127.0.0.1:$DashboardPort/healthz").StatusCode -eq 200 } catch { $false } }
function Start-Dashboard {
  if (-not (Dashboard-Online)) {
    Start-Process -FilePath $PythonPath -ArgumentList @('scripts\run_local_dashboard.py','--port',$DashboardPort,'--profile',$Profile) -WorkingDirectory $ProjectRoot -WindowStyle Hidden
  }
  return $true
}

function New-BigQmtTrayIcon([string]$ProfileName) {
  # Generate a dependency-free icon so the two profiles are visibly distinct.
  $bitmap = New-Object Drawing.Bitmap(32, 32)
  $graphics = [Drawing.Graphics]::FromImage($bitmap)
  $graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $graphics.Clear([Drawing.Color]::Transparent)
  $color = if ($ProfileName -eq 'simulation') { [Drawing.Color]::FromArgb(37, 99, 235) } else { [Drawing.Color]::FromArgb(124, 58, 237) }
  $brush = New-Object Drawing.SolidBrush($color)
  $graphics.FillEllipse($brush, 1, 1, 30, 30)
  $font = New-Object Drawing.Font('Segoe UI', 16, [Drawing.FontStyle]::Bold, [Drawing.GraphicsUnit]::Pixel)
  $letter = if ($ProfileName -eq 'simulation') { 'S' } else { 'P' }
  $format = New-Object Drawing.StringFormat
  $format.Alignment = [Drawing.StringAlignment]::Center
  $format.LineAlignment = [Drawing.StringAlignment]::Center
  $graphics.DrawString($letter, $font, [Drawing.Brushes]::White, [Drawing.RectangleF]::new(0, 0, 32, 32), $format)
  $handle = $bitmap.GetHicon()
  # Icon.FromHandle merely borrows an HICON.  Returning that borrowed Icon
  # allows the Bitmap to be collected and makes Windows display a blank or
  # missing notification-area icon.  Clone it into an owned Icon before
  # disposing the GDI drawing objects.
  $borrowedIcon = [Drawing.Icon]::FromHandle($handle)
  $icon = [Drawing.Icon]$borrowedIcon.Clone()
  $borrowedIcon.Dispose()
  $graphics.Dispose(); $brush.Dispose(); $font.Dispose(); $format.Dispose(); $bitmap.Dispose()
  return $icon
}

$notify = New-Object Windows.Forms.NotifyIcon
Write-TrayEvent 'tray_ui_initializing' 'creating profile-specific notification icon'
# Use Windows-owned icons for the operational tray.  The previous dynamically
# created HICON could be discarded by the shell even while the PowerShell
# process stayed alive, yielding an invisible tray.  The two standard icons
# remain clearly distinct and survive Explorer/taskbar refreshes.
$trayIcon = if ($Profile -eq 'simulation') { [Drawing.SystemIcons]::Information } else { [Drawing.SystemIcons]::Shield }
$notify.Icon = $trayIcon
$notify.Visible = $true
Write-TrayEvent 'tray_icon_ready' 'notification icon assigned'
$menu = New-Object Windows.Forms.ContextMenuStrip
$open = $menu.Items.Add("Open $profileLabel Dashboard")
$windowsStartup = New-Object Windows.Forms.ToolStripMenuItem('Start this BigQMT tray with Windows')
$windowsStartup.CheckOnClick = $false
$windowsStartup.Checked = Test-WindowsStartupEnabled
[void]$menu.Items.Add($windowsStartup)
$simulationStrategyRun = New-Object Windows.Forms.ToolStripMenuItem('Enable v1.1.15 simulated strategy execution')
$simulationStrategyRun.CheckOnClick = $false
$simulationStrategyRun.Visible = ($Profile -eq 'simulation')
$simulationStrategyRun.Checked = Test-SimulationStrategyRunEnabled
[void]$menu.Items.Add($simulationStrategyRun)
$formalStrategyRecovery = New-Object Windows.Forms.ToolStripMenuItem('Allow recovery of approved formal strategies')
$formalStrategyRecovery.CheckOnClick = $false
$formalStrategyRecovery.Visible = ($Profile -eq 'production_readonly')
$formalStrategyRecovery.Checked = Test-FormalStrategyRecoveryEnabled
$formalStrategyRecovery.ToolTipText = 'This does not unlock orders or approve any strategy. It only permits future recovery of separately admitted formal strategies after all gates pass.'
[void]$menu.Items.Add($formalStrategyRecovery)
$startQmt = $menu.Items.Add('Start missing QMT terminal')
$restartQmt = $menu.Items.Add('Restart this QMT terminal')
$start = $menu.Items.Add('Ensure local read-only Dashboard is running')
$startRedis = $menu.Items.Add('Ensure profile Redis is running')
$lock = $menu.Items.Add('Lock orders (fail-closed)')
$lake = $menu.Items.Add('Run read-only lake cycle')
$shadow = $menu.Items.Add('Run v1.1.15 close shadow (no orders)')
$cyclePreflight = $menu.Items.Add('Preflight v1.1.15 next-session cycle (no orders)')
$cycleExecute = $menu.Items.Add('Execute one preflighted v1.1.15 simulation action')
$dailyRecord = $menu.Items.Add('Record v1.1.15 daily operations (read-only)')
[void]$menu.Items.Add((New-Object Windows.Forms.ToolStripSeparator))
$state = $menu.Items.Add('Checking local state...'); $state.Enabled = $false
$bridgeState = $menu.Items.Add('Bridge snapshot: checking...'); $bridgeState.Enabled = $false
$bridgeLiveState = $menu.Items.Add('Bridge live ping: checking...'); $bridgeLiveState.Enabled = $false
$qmtState = $menu.Items.Add('QMT: checking...'); $qmtState.Enabled = $false
$redisState = $menu.Items.Add('Redis: checking...'); $redisState.Enabled = $false
$dashboardState = $menu.Items.Add('Dashboard: checking...'); $dashboardState.Enabled = $false
$lockState = $menu.Items.Add('Order lock: checking...'); $lockState.Enabled = $false
$strategyState = $menu.Items.Add('Strategy execution: checking...'); $strategyState.Enabled = $false
$log = $menu.Items.Add('Open local audit folder')
[void]$menu.Items.Add((New-Object Windows.Forms.ToolStripSeparator))
$exit = $menu.Items.Add('Exit Tray')
Write-TrayEvent 'tray_menu_ready' 'menu assigned'

if ($Profile -eq 'production_readonly') {
  $open.ToolTipText = 'Formal read-only projection: no strategy execution, order, or cancel capability.'
}

function Refresh-State {
  try {
    $s = Invoke-Project @('status')
    $h = Invoke-Health
    $q = Invoke-QmtLauncher @('status')
    $checks = @{}
    foreach ($check in @($h.checks)) { $checks[[string]$check.name] = [string]$check.status }
    $displayHealth = [string]$h.overall
    $liveStatus = [string]$script:lastBridgeProbe.status
    if ($liveStatus -ne 'PASS' -and $displayHealth -eq 'HEALTHY') { $displayHealth = 'DEGRADED' }
    $state.Text = "$profileLabel | Health: $displayHealth | Runtime: $($s.mode) | Orders: LOCKED"
    $bridgeState.Text = "Bridge snapshot: " + $(if ($checks.ContainsKey('bridge_snapshot')) { $checks['bridge_snapshot'] } else { 'UNKNOWN' })
    $bridgeLiveState.Text = "Bridge live ping: " + $liveStatus + " (read-only)"
    if ($q.ok) {
      $portState = if ($q.formula_server_listening) { 'LISTENING' } else { 'WAITING' }
      $qmtState.Text = "QMT: " + [string]$q.status + " (PROCESS ONLY) | FormulaServer " + [string]$q.formula_server_port + ': ' + $portState
    } else {
      $qmtState.Text = 'QMT: STATUS ERROR'
    }
    $redisState.Text = "Redis: " + $(if ($checks.ContainsKey('redis')) { $checks['redis'] } else { 'UNKNOWN' })
    $dashboardState.Text = "Dashboard: " + $(if ($checks.ContainsKey('dashboard')) { $checks['dashboard'] } else { 'UNKNOWN' })
    $lockState.Text = "Order lock: " + $(if ($checks.ContainsKey('order_lock')) { $checks['order_lock'] } else { 'UNKNOWN' })
    $windowsStartup.Checked = Test-WindowsStartupEnabled
    if ($Profile -eq 'simulation') {
      $simulationStrategyRun.Checked = Test-SimulationStrategyRunEnabled
      $strategyState.Text = "Strategy execution: " + $(if ($simulationStrategyRun.Checked) { 'ENABLED (v1.1.15 only)' } else { 'PAUSED (no order cycle)' })
    } else {
      $formalStrategyRecovery.Checked = Test-FormalStrategyRecoveryEnabled
      $strategyState.Text = "Strategy recovery: " + $(if ($formalStrategyRecovery.Checked) { 'INTENT ON / NO STRATEGY ADMITTED' } else { 'NOT AUTHORIZED' })
    }
    $notify.Text = "BigQMT ${profileLabel}: $displayHealth / orders locked"
    if ([string]$h.overall -ne $script:lastHealth) {
      Write-TrayEvent 'health_changed' ([string]$h.overall)
      $script:lastHealth = [string]$h.overall
    }
  } catch {
    $state.Text = "$profileLabel | Runtime: unavailable (locked)"
    $bridgeState.Text = 'Bridge snapshot: UNAVAILABLE'
    $bridgeLiveState.Text = 'Bridge live ping: UNAVAILABLE'
    $qmtState.Text = 'QMT: UNAVAILABLE'
    $redisState.Text = 'Redis: UNAVAILABLE'
    $dashboardState.Text = 'Dashboard: UNAVAILABLE'
    $lockState.Text = 'Order lock: FAIL_CLOSED'
    $strategyState.Text = $(if ($Profile -eq 'simulation') { 'Strategy execution: UNAVAILABLE / PAUSED' } else { 'Strategy recovery: FORMAL READ-ONLY / NOT AUTHORIZED' })
    $notify.Text = "BigQMT ${profileLabel}: runtime unavailable"
    if ($script:lastHealth -ne 'FAIL_CLOSED') {
      Write-TrayEvent 'health_changed' 'FAIL_CLOSED'
      $script:lastHealth = 'FAIL_CLOSED'
    }
    Write-TrayEvent 'health_error' $_.Exception.Message
  }
}
$open.add_Click({ if (Start-Dashboard) { Start-Process "http://127.0.0.1:$DashboardPort$dashboardRoute" } })
$windowsStartup.add_Click({
  try {
    Set-WindowsStartup (-not (Test-WindowsStartupEnabled))
    $windowsStartup.Checked = Test-WindowsStartupEnabled
  } catch {
    $windowsStartup.Checked = Test-WindowsStartupEnabled
    Write-TrayEvent 'windows_startup_error' $_.Exception.Message
    [Windows.Forms.MessageBox]::Show('Unable to update the Windows startup setting. See the local audit log.', 'BigQMT Tray', 'OK', 'Warning') | Out-Null
  }
})
$simulationStrategyRun.add_Click({
  if ($Profile -ne 'simulation') { return }
  try {
    Set-SimulationStrategyRunEnabled (-not (Test-SimulationStrategyRunEnabled))
    $simulationStrategyRun.Checked = Test-SimulationStrategyRunEnabled
    Refresh-State
  } catch {
    $simulationStrategyRun.Checked = Test-SimulationStrategyRunEnabled
    Write-TrayEvent 'simulation_strategy_switch_error' $_.Exception.Message
    [Windows.Forms.MessageBox]::Show('Unable to update the simulation strategy switch. See the local audit log.', 'BigQMT Tray', 'OK', 'Warning') | Out-Null
  }
})
$formalStrategyRecovery.add_Click({
  if ($Profile -ne 'production_readonly') { return }
  $next = -not (Test-FormalStrategyRecoveryEnabled)
  if ($next) {
    $confirm = [Windows.Forms.MessageBox]::Show('This only records recovery intent. It does not unlock orders and does not approve any strategy. Enable this intent?', 'BigQMT Tray', 'YesNo', 'Warning')
    if ($confirm -ne 'Yes') { return }
  }
  try {
    Set-FormalStrategyRecoveryEnabled $next
    $formalStrategyRecovery.Checked = Test-FormalStrategyRecoveryEnabled
    Refresh-State
  } catch {
    $formalStrategyRecovery.Checked = Test-FormalStrategyRecoveryEnabled
    Write-TrayEvent 'formal_strategy_recovery_switch_error' $_.Exception.Message
    [Windows.Forms.MessageBox]::Show('Unable to update the formal strategy recovery setting. See the local audit log.', 'BigQMT Tray', 'OK', 'Warning') | Out-Null
  }
})
$startQmt.add_Click({ Ensure-QmtStarted | Out-Null; Refresh-State })
$restartQmt.add_Click({
  $confirm = [Windows.Forms.MessageBox]::Show('Restart only this profile''s QMT terminal? The tray will not restart it automatically; this action closes its QMT processes and starts the configured terminal again.', 'BigQMT Tray', 'YesNo', 'Warning')
  if ($confirm -ne 'Yes') { return }
  try {
    $result = Invoke-QmtLauncher @('restart')
    Write-TrayEvent $(if ($result.ok) { 'qmt_restart_requested' } else { 'qmt_restart_failed' }) ("result=" + [string]$result.result + "; error=" + [string]$result.error)
    Refresh-State
  } catch {
    Write-TrayEvent 'qmt_restart_error' $_.Exception.Message
    [Windows.Forms.MessageBox]::Show('QMT restart could not be requested. See the local audit log.', 'BigQMT Tray', 'OK', 'Warning') | Out-Null
  }
})
$start.add_Click({ Ensure-Redis | Out-Null; Start-Dashboard; Refresh-State })
$startRedis.add_Click({ Ensure-Redis | Out-Null; Refresh-State })
$lock.add_Click({ Invoke-Project @('lock-orders','--reason','BigQMT Tray operator lock') | Out-Null; Write-TrayEvent 'operator_lock' 'orders remain disabled'; Refresh-State })
$lake.add_Click({ try { $result = Invoke-LakeCycle; Write-TrayEvent 'lake_cycle' ("status=" + [string]$result.status + "; export_returncode=" + [string]$result.export_returncode + "; evidence=" + [string]$result.evidence_path); $kind = if ([string]$result.status -eq 'PASSED') { 'Information' } else { 'Warning' }; [Windows.Forms.MessageBox]::Show(("Lake cycle: " + [string]$result.status + "`nEvidence: " + [string]$result.evidence_path), 'BigQMT Tray', 'OK', $kind) | Out-Null } catch { Write-TrayEvent 'lake_cycle_error' $_.Exception.Message; [Windows.Forms.MessageBox]::Show('Lake cycle blocked; see tray audit log.', 'BigQMT Tray', 'OK', 'Warning') | Out-Null } })
$shadow.add_Click({ try { $result = Invoke-CloseShadow; Write-TrayEvent 'v1_1_15_close_shadow_manual' ("result=" + [string]$result.result + "; day=" + [string]$result.signal_day + "; target=" + [string]$result.desired_qmt + "; orders_enabled=false"); [Windows.Forms.MessageBox]::Show(("v1.1.15 close shadow: " + [string]$result.result + "`nSignal day: " + [string]$result.signal_day + "`nTarget: " + [string]$result.desired_qmt + "`nOrders: LOCKED"), 'BigQMT Tray', 'OK', 'Information') | Out-Null } catch { Write-TrayEvent 'v1_1_15_close_shadow_manual_error' $_.Exception.Message; [Windows.Forms.MessageBox]::Show('Close shadow blocked; see tray audit log.', 'BigQMT Tray', 'OK', 'Warning') | Out-Null } })
$cyclePreflight.add_Click({ try { $result = Invoke-V1_1_15SimulationCycle $false; Write-TrayEvent 'v1_1_15_cycle_preflight_manual' ("status=" + [string]$result.status + "; evidence=" + [string]$result.evidence); [Windows.Forms.MessageBox]::Show(("v1.1.15 cycle preflight: " + [string]$result.status + "`nEvidence: " + [string]$result.evidence + "`nNo order was sent."), 'BigQMT Tray', 'OK', 'Information') | Out-Null } catch { Write-TrayEvent 'v1_1_15_cycle_preflight_error' $_.Exception.Message; [Windows.Forms.MessageBox]::Show('Cycle preflight blocked; see tray audit log.', 'BigQMT Tray', 'OK', 'Warning') | Out-Null } })
$cycleExecute.add_Click({ if (-not (Test-SimulationStrategyRunEnabled)) { [Windows.Forms.MessageBox]::Show('The simulated strategy is paused. Enable “v1.1.15 simulated strategy execution” first.', 'BigQMT Tray', 'OK', 'Information') | Out-Null; return }; $confirm = [Windows.Forms.MessageBox]::Show('Simulation only: submit at most one v1.1.15 action after fresh quote, account, order, sleeve and reconciliation checks? Orders lock again immediately after the response.', 'BigQMT Tray', 'YesNo', 'Warning'); if ($confirm -ne 'Yes') { return }; try { $result = Invoke-V1_1_15SimulationCycle $true; Write-TrayEvent 'v1_1_15_cycle_execute_manual' ("status=" + [string]$result.status + "; evidence=" + [string]$result.evidence); [Windows.Forms.MessageBox]::Show(("v1.1.15 execution cycle: " + [string]$result.status + "`nEvidence: " + [string]$result.evidence + "`nOrders are locked after this cycle."), 'BigQMT Tray', 'OK', 'Information') | Out-Null; Refresh-State } catch { Write-TrayEvent 'v1_1_15_cycle_execute_error' $_.Exception.Message; [Windows.Forms.MessageBox]::Show('Execution cycle blocked; see tray audit log.', 'BigQMT Tray', 'OK', 'Warning') | Out-Null; Refresh-State } })
$dailyRecord.add_Click({ try { $result = Invoke-DailyOperationsRecord; Write-TrayEvent 'v1_1_15_daily_operations_record_manual' ("status=" + [string]$result.status + "; nav=" + [string]$result.nav + "; evidence=" + [string]$result.evidence); [Windows.Forms.MessageBox]::Show(("Daily operations: " + [string]$result.status + "`nNAV: " + [string]$result.nav + "`nEvidence: " + [string]$result.evidence), 'BigQMT Tray', 'OK', 'Information') | Out-Null } catch { Write-TrayEvent 'v1_1_15_daily_operations_record_manual_error' $_.Exception.Message; [Windows.Forms.MessageBox]::Show('Daily operations record blocked; see tray audit log.', 'BigQMT Tray', 'OK', 'Warning') | Out-Null } })
$log.add_Click({ $path = Join-Path $ProjectRoot ("runtime_data\audit\" + $Profile); New-Item -ItemType Directory -Force -Path $path | Out-Null; Start-Process $path })
$exit.add_Click({ [Windows.Forms.Application]::Exit() })
$notify.ContextMenuStrip = $menu
$notify.add_DoubleClick({ if (Start-Dashboard) { Start-Process "http://127.0.0.1:$DashboardPort$dashboardRoute" } })
$timer = New-Object Windows.Forms.Timer; $timer.Interval = 15000; $timer.add_Tick({ Ensure-Redis | Out-Null; Ensure-QmtStarted | Out-Null; Start-Dashboard | Out-Null; Invoke-BridgeProbeIfDue | Out-Null; Refresh-State; Invoke-HourlyAccountSnapshotIfDue; Invoke-V1_1_15SimulationCycleIfDue; Invoke-CloseShadowIfDue; Invoke-LakeCycleIfDue; Invoke-DailyOperationsRecordIfDue }); Ensure-Redis | Out-Null; Ensure-QmtStarted | Out-Null; Start-Dashboard | Out-Null; Invoke-BridgeProbeIfDue | Out-Null; Refresh-State; Invoke-HourlyAccountSnapshotIfDue; Write-TrayEvent 'tray_message_loop_starting' 'timer started; supervisory_interval_seconds=15; account_snapshot_interval_seconds=3600'; $timer.Start()
try { [Windows.Forms.Application]::Run() } finally { Write-TrayEvent 'tray_stopped' 'operator process stopped'; $timer.Stop(); $notify.Visible = $false; $notify.Dispose(); $menu.Dispose(); try { $mutex.ReleaseMutex() } catch {}; $mutex.Dispose() }
