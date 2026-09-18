# `.113` 主机：VS Code（Claude）执行说明

你现在是在 `.113` Windows 策略运行主机执行任务。请严格按顺序完成，不要删除用户文件，不要修改 QMT 内的 `BIGQMT_BRIDGE` 策略，不要下单。

## 1. 工作目录和分支

GitHub 仓库地址是：

```text
https://github.com/kitling-cax/Bigqmt.git
```

如果工作目录尚未初始化或没有 `origin`，先执行：

```powershell
Set-Location '<LOCAL_BIGQMT_ROOT>'
if (-not (Test-Path '.git')) { git clone https://github.com/kitling-cax/Bigqmt.git . }
git remote -v
git remote set-url origin https://github.com/kitling-cax/Bigqmt.git
```

如 GitHub 要求登录，使用本机已配置的 Git Credential Manager、SSH Key 或 GitHub PAT；不要把 PAT 写入脚本、配置文件、Fact Secret 或提交记录。

```powershell
Set-Location '<LOCAL_BIGQMT_ROOT>'
git status --short
git fetch origin --prune
```

如果 `git status` 显示已有未提交改动，先报告文件列表，不得 reset、clean 或覆盖。确认工作区可操作后，使用 `.113` 主机分支：

```powershell
git show-ref --verify --quiet refs/remotes/origin/host/113
if ($LASTEXITCODE -eq 0) {
  git switch host/113 2>$null
  if ($LASTEXITCODE -ne 0) { git switch --track origin/host/113 }
} else {
  git switch -c host/113 --track origin/main
}
git pull --ff-only
```

## 2. 检查本机配置

只修改本机未跟踪文件 `config/machine.local.json`，不得提交该文件：

> 本文在 GitHub 中是脱敏版。`<...>` 项必须从本机已有的 `machine.local.json`、NAS 私有配置或管理员提供的本机配置中填写，不能原样作为真实路径或账户号使用。

```json
{
  "schema_version": 1,
  "data_directory": "E:/kitling_QMT_work/kitling_bigqmt/runtime_data",
  "coordinator": {
    "endpoint": "http://<COORDINATOR_HOST>:18443",
    "host_id": "<HOST_113_ID_FROM_LOCAL_CONFIG>"
  },
  "host_agent": {
    "fact_secret_path": "C:/ProgramData/Kitling/BigQMT/host-facts/host-113-fact-shadow-20260917.json"
  },
  "environments": {
    "simulation": {
      "account_id": "<SIMULATION_ACCOUNT_ID_FROM_LOCAL_CONFIG>",
      "qmt_root": "<SIMULATION_QMT_ROOT>",
      "redis": {"host": "127.0.0.1", "port": 6379, "db": 5},
      "dashboard_port": 17890,
      "ready_port": 58600
    },
    "production_readonly": {
      "account_id": "<PRODUCTION_ACCOUNT_ID_FROM_LOCAL_CONFIG>",
      "qmt_root": "<PRODUCTION_QMT_ROOT>",
      "redis": {"host": "127.0.0.1", "port": 6380, "db": 5},
      "dashboard_port": 17891,
      "ready_port": 58600
    }
  }
}
```

确认以下文件存在；缺少 Fact Secret 时停止并报告，不得从 `.125` 复制：

```powershell
Test-Path '<FACT_SECRET_PATH_FROM_LOCAL_CONFIG>'
Test-Path '<SIMULATION_QMT_ROOT>\bin.x64'
Test-Path '<PRODUCTION_QMT_ROOT>\bin.x64'
```

## 3. 编译两个账户托盘

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_native_account_trays.ps1
Get-Content tray\BigQMT_native_tray_checksums.sha256
```

编译失败时保留错误输出，不要自行修改 Bridge 或 QMT 文件。

## 4. 停止旧托盘并启动新托盘

只停止托盘进程；不要停止 QMT、MiniQMT、Redis、Bridge 或 Dashboard：

```powershell
Get-Process BigQMT_Simulation,BigQMT_Production_ReadOnly,BigQMT_HostTray -ErrorAction SilentlyContinue | Stop-Process
Start-Process '<LOCAL_BIGQMT_ROOT>\tray\BigQMT_Simulation.exe'
Start-Process '<LOCAL_BIGQMT_ROOT>\tray\BigQMT_Production_ReadOnly.exe'
```

不再启动独立 `BigQMT_HostTray.exe`。Host Agent 已经内置到账户托盘。

## 5. 验证

等待约 30 秒后执行：

```powershell
Get-Process BigQMT_Simulation,BigQMT_Production_ReadOnly -ErrorAction SilentlyContinue | Select-Object ProcessName,Id
Get-Content runtime_data\audit\simulation\native_tray.jsonl -Tail 20
Get-Content runtime_data\audit\production_readonly\native_tray.jsonl -Tail 20
Invoke-RestMethod '<COORDINATOR_ENDPOINT_FROM_LOCAL_CONFIG>/api/v1/hosts' | ConvertTo-Json -Depth 8
```

托盘菜单中应看到：

```text
Host Agent：心跳正常｜本机 Host ID｜只读服务已上报
```

然后打开“服务管理 → 立即同步 Host Agent（只读）”，确认日志出现心跳或事实投递结果。此阶段只能上报只读事实，不能申请租约、确认意图或下单。

## 6. 回传源码

只提交通用源码、示例配置、文档和校验文件；绝对不要提交 `config/machine.local.json`、Fact Secret、QMT密码、`runtime_data` 或本机日志：

```powershell
git status --short
git add tray/BigQMTAccountTray.cs tray/BigQMT_native_tray_checksums.sha256 config/machine.local.example.json config/schemas/machine.local.schema.json docs/161_host_agent_embedded_account_tray_2026-09-18.md
git commit -m "feat: embed readonly host agent in account tray"
git push -u origin host/113
```

完成后报告：分支、提交SHA、两个EXE哈希、Host Agent心跳结果和任何阻塞项。
