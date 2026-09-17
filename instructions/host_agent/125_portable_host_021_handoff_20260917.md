# `.125` Portable Host Tray 0.2.1 交接（替代 0.2.0）

不要运行 `BigQMT_Host_125` 旧目录中的 0.2.0。它把 Fact Secret 配在包内，首次
初始化会被安全保护拒绝。旧目录保留作审计，不要删除或覆盖。

## 唯一使用目录

```text
E:\kitling_QMT_work\kitling_bigqmt\BigQMT_Host_125_0.2.1
```

本机用 Windows PowerShell（不是 Bash/WSL）执行：

```powershell
cd E:\kitling_QMT_work\kitling_bigqmt\BigQMT_Host_125_0.2.1
Get-Content .\checksums.sha256 | ForEach-Object {
  if ($_ -match '^([A-F0-9]+)  (.+)$') {
    if ((Get-FileHash -LiteralPath $matches[2] -Algorithm SHA256).Hash -ne $matches[1]) {
      throw "checksum mismatch: $($matches[2])"
    }
  }
}
Get-Content .\machine.local.json
.\start_host_tray.cmd
```

## 预期配置与结果

- `host_id` 必须是 `192.0.2.125`；
- `orders_enabled` 必须是 `false`；
- endpoint 必须是 `http://192.0.2.121:18666/api/v1/facts/ingest`；
- Fact Secret 会在**本机**创建于
  `C:\ProgramData\Kitling\BigQMT\host-facts\host-125-fact-shadow-20260917.json`，
  不在包内、不上传 NAS；
- SQLite Outbox 仍在包内 `state\simulation\`；
- 缺少原生账户托盘审计日志时，托盘显示红色等待状态是正确行为；不得用该 Host
  Agent 启动 QMT 或创建订单。

## 严格禁止

不要在 Git Bash 中用 `ls/find` 验证 Windows UNC 路径；那会把可用 SMB 路径误报为
不存在。不要复制、打印、上传 Secret；不要访问/修改 `.121:18443`；不要创建
授权 Key、执行租约、订单或交易指令。

只报告校验结果、托盘状态、审计日志是否存在、Secret 文件是否存在（是/否）和
Outbox pending 数。新的 Secret 尚未受 Shadow 信任；首次投递待重试是预期状态。
