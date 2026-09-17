# `.125` VS Code + Claude 执行清单：Host Agent 0.1.0 Shadow

目标主机：`192.0.2.125`

执行人：`.125` Windows 侧 VS Code 中的 Claude 插件

范围：只安装 facts-only Host Agent，向 `.121:18666` Shadow 上报运行事实。不安装或启用任何订单、Lease、确认、QMT 写入或 Redis 写入能力。

## 一、必须遵守的边界

1. Host Agent 在 **Windows PowerShell** 中运行，不在 WSL 中运行。
2. OpenClaw/Claude 只负责执行安装、检查和报告；Host Agent 是独立本地程序。
3. 不读取、显示、复制或上传 Fact Secret 内容。
4. 不把 Secret 放入 NAS、VS Code 工作区、Git 或 OpenClaw 报告。
5. 只允许使用：

```text
http://192.0.2.121:18666/api/v1/facts/ingest
```

6. 禁止访问权威事实写入口 `18443`，禁止运行任何下单或 Lease 命令。

## 二、VS Code 准备

在 `.125` Windows 中：

1. 打开 VS Code。
2. 以管理员身份启动 VS Code，或以管理员身份打开 Windows PowerShell 终端。
3. 使用 **PowerShell**，不要使用 WSL 终端。
4. 确认 Python：

```powershell
py -3.12 --version
```

如果没有 Python 3.12，不要自行改用未知 Python 或自动安装软件；在报告中标记 `BLOCKED_PYTHON_312_MISSING`，等待确认。

## 三、复制候选包到本机

NAS 源目录：

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\releases\host_agent\candidate\0.1.0-shadow
```

复制到 Windows 本机：

```powershell
$src = '\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\releases\host_agent\candidate\0.1.0-shadow'
$dst = 'C:\ProgramData\Kitling\BigQMT\HostAgent\0.1.0-shadow'
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Path ($src + '\*') -Destination $dst -Recurse -Force
```

检查清单文件存在：

```powershell
Test-Path "$dst\checksums.sha256"
Test-Path "$dst\scripts\host_agent\collect_runtime_fact.py"
Test-Path "$dst\scripts\host_agent\deliver_fact_outbox.py"
```

必须验证 `checksums.sha256` 与 NAS 版本一致；发现不一致立即停止。

## 四、确认本机托盘审计路径

只读查找，不要修改任何 QMT 文件：

```powershell
Get-ChildItem -Path 'C:\kitling_bigqmt','D:\kitling_bigqmt','E:\kitling_bigqmt','C:\BigQMT\work\kitling_bigqmt' -Filter native_tray.jsonl -Recurse -File -ErrorAction SilentlyContinue |
  Select-Object -First 20 FullName,Length,LastWriteTime
```

选择 `.125` 本机真实存在的模拟托盘日志：

```text
<PROJECT_ROOT>\runtime_data\audit\simulation\native_tray.jsonl
```

如果找不到日志，停止并报告 `BLOCKED_NATIVE_TRAY_AUDIT_MISSING`，不要创建伪造日志。

## 五、生成 `.125` 独立 Fact Secret

先创建受保护目录：

```powershell
$secretDir = 'C:\ProgramData\Kitling\BigQMT\secrets'
New-Item -ItemType Directory -Force -Path $secretDir | Out-Null
```

生成 Secret（脚本只输出 host_id 和 key_id，不输出 Secret）：

```powershell
py -3.12 "$dst\scripts\coordinator\manage_fact_identity.py" `
  --host-id 192.0.2.125 `
  --key-id host-125-fact-shadow-20260917 `
  --output "$secretDir\host-125-fact-shadow.json"
```

设置 ACL：

```powershell
icacls "$secretDir\host-125-fact-shadow.json" /inheritance:r /grant:r `
  'SYSTEM:(F)' 'BUILTIN\Administrators:(F)' "$env:USERDOMAIN\$env:USERNAME:(F)"
```

禁止执行 `Get-Content` 查看 Secret 内容。

## 六、准备 `.125` 本地配置和 Outbox

```powershell
$project = '<PROJECT_ROOT>'
$audit = Join-Path $project 'runtime_data\audit\simulation\native_tray.jsonl'
$outbox = 'C:\ProgramData\Kitling\BigQMT\HostAgent\state\simulation\host_agent_outbox.sqlite3'
New-Item -ItemType Directory -Force -Path (Split-Path $outbox) | Out-Null
```

将 `config\machine.local.example.json` 复制为本机配置，并把 `host_id` 改成 `192.0.2.125`；配置文件中不得写 Secret 内容，只能写 Secret 路径。

## 七、首次本地采集

```powershell
py -3.12 "$dst\scripts\host_agent\collect_runtime_fact.py" `
  --profile simulation `
  --host-id 192.0.2.125 `
  --audit-path "$audit" `
  --outbox-path "$outbox"
```

预期：

```text
status=QUEUED 或 DUPLICATE
account_id=90000001
orders_enabled=false
```

## 八、首次 Shadow 投递

```powershell
py -3.12 "$dst\scripts\host_agent\deliver_fact_outbox.py" `
  --profile simulation `
  --secret-file "$secretDir\host-125-fact-shadow.json" `
  --outbox-path "$outbox" `
  --endpoint 'http://192.0.2.121:18666/api/v1/facts/ingest'
```

成功标准：

```text
status=ACCEPTED 或 EMPTY
facts_only=true
orders_enabled=false
pending=0
```

网络失败时预期为 `RETRY_PENDING`，且 pending 必须保留；不得手动删除 Outbox。

## 九、生成安装报告

报告路径：

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\reports\openclaw\125\20260917_host_agent_install_report.md
```

报告只写以下内容：

- 主机 ID：`192.0.2.125`
- 包版本：`0.1.0-shadow`
- checksums 校验结果
- Python 版本
- 本地采集结果
- Shadow HTTP 状态和 `facts_only/orders_enabled` 字段
- Outbox pending 数量
- 是否创建任务计划（本轮先不自动创建）
- 错误摘要

报告禁止包含：

- Secret 内容
- 密码
- token
- 执行 Key
- 完整授权文件

## 十、完成后回报格式

Claude 只需回报：

```text
HOST_AGENT_125_RESULT=PASSED 或 BLOCKED
host_id=192.0.2.125
package=0.1.0-shadow
shadow_endpoint=http://192.0.2.121:18666/api/v1/facts/ingest
facts_only=true
orders_enabled=false
pending=<数量>
report=<NAS报告路径>
```

本次完成后不要注册新的 OpenClaw 下单工具，不要修改 `18443`，不要启动任何订单流程。
