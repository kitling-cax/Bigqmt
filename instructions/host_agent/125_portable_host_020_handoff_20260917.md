# `.125` Portable Host Tray 0.2.0 交接

目标 Windows 主机：`192.0.2.125`。本任务只部署事实采集托盘，不授予
下单、租约、确认、QMT RPC 或 Redis 写入能力。

## 0. 清理旧候选（只确认，不删除新包）

确认此前手工安装的 `host_agent_candidate` 不再运行：关闭其窗口、停止其
计划任务（如有）并确认没有旧的 Host Agent Python/EXE 进程。不要删除任何
QMT、BigQMT 账户托盘、Redis、Dashboard 或 Coordinator 文件。

## 1. 新包位置

新包已经在本机共享工作目录：

```text
E:\kitling_QMT_work\kitling_bigqmt\BigQMT_Host_125
```

先在 PowerShell 中验证清单：

```powershell
cd E:\kitling_QMT_work\kitling_bigqmt\BigQMT_Host_125
Get-Content .\checksums.sha256 | ForEach-Object {
  if ($_ -match '^([A-F0-9]+)  (.+)$') {
    $actual = (Get-FileHash -LiteralPath $matches[2] -Algorithm SHA256).Hash
    if ($actual -ne $matches[1]) { throw "checksum mismatch: $($matches[2])" }
  }
}
```

## 2. 仅检查配置

打开 `machine.local.json`，确认：

- `host_id` 是 `192.0.2.125`；
- `coordinator_endpoint` 是 `http://192.0.2.121:18666/api/v1/facts/ingest`；
- `orders_enabled` 是 `false`；
- `audit_path` 指向 `.125` 本机的原生 BigQMT 账户托盘审计日志。

默认相对路径假定本机项目根已有：

```text
E:\kitling_QMT_work\kitling_bigqmt\runtime_data\audit\simulation\native_tray.jsonl
```

如果本机账户托盘尚未部署或还没有该日志，保持默认即可；新托盘会启动为红色
“等待审计日志”状态，不会启动 QMT 或创建任何下单行为。

## 3. 首次启动

在 Windows（不要在 WSL）双击 `start_host_tray.cmd`，或执行：

```powershell
.\start_host_tray.cmd
```

首次启动在本机 `secrets\host-fact.json` 生成独立 Fact Secret 并收紧 NTFS ACL，
在 `state\simulation\` 创建 SQLite WAL Outbox。不要复制、打印、上传或提交
该 Secret。

## 4. 回报内容

仅报告下列非敏感信息：

- 托盘是否可见、颜色和状态文字；
- `logs\host_agent_tray.jsonl` 最新一行的事件名（不要贴 secret）；
- `secrets\host-fact.json` 是否存在（只回答存在/不存在）；
- `machine.local.json` 的 `host_id` 和 endpoint；
- 是否发现可读取的原生审计日志。

不要尝试把新 Host Secret 传给 `.121`，不要修改 `18443`，不要创建授权 Key、
执行租约或订单。`18666` 目前只会接受已受信任的事实身份，因此新主机首次投递
可能显示待重试；这属于预期状态，等待下一阶段受控注册。
