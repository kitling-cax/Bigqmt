# `.113` 今日非交易日正式 Bridge 只读恢复检查

今天确认 A 股不交易后即可执行。该流程不开放订单，不修改桥接代码。

## 1. 记录重启前状态

```powershell
Set-Location E:\kitling_QMT_work\kitling_bigqmt
Get-Content runtime_data\audit\production_readonly\native_tray.jsonl -Tail 30
py -3.12 scripts\probe_host_agent_intent_preview.py `
  --endpoint http://192.168.1.121:18443 `
  --host-id 10.10.10.113 `
  --account-id 90000002
```

确认当前 `orders_enabled=false`、`broker_call_made=false`。

## 2. 受控重启

使用 `.113` 本机托盘菜单或既有 QMT 运维方式，依次重启：

1. 正式 QMT 的策略/Bridge 进程；
2. 等待正式 QMT 登录和 Redis 6380 恢复；
3. 不要启动任何下单测试，不要切换正式账户权限。

今天可以执行；交易日仍禁止在交易时段执行。不要自动 stop/start Redis，不要修改 `machine.local.json`。

## 3. 只读验证

```powershell
Test-NetConnection 127.0.0.1 -Port 6380
Get-Content runtime_data\audit\production_readonly\native_tray.jsonl -Tail 50
```

验收条件：

- `bridge_auto_probe=PASS`；
- Redis 6380 使用 `runtime_data\redis\production_readonly`；
- `broker_call_made=false`；
- `order_capability=false`；
- `orders_enabled=false`；
- Fact pending 仍为 0。

如果仍然 `DEGRADED`，停止继续重启，保留最近日志并回报错误类型、耗时和 QMT/Redis 状态。
