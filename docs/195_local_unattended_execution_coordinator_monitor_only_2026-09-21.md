# 本机无人值守执行与 Coordinator 监控边界（2026-09-21）

## 已确定的边界

- `Coordinator` 只负责心跳、服务状态、策略运行状态、收益/成交事实和重复运行告警。
- 本机策略执行不请求 Coordinator 许可，不依赖 Coordinator 在线，也不接受 120 秒临时执行窗口。
- 模拟账户的执行权限由本机授权 Key、策略开关、本机运行控制、交易时段、QMT/Redis/Bridge 探活、持仓对账共同决定。
- 正式账户仍保持 `PRODUCTION_READ_ONLY`，没有本机授权 Key 也不能执行正式订单。

## 本机持久执行状态

本机 `machine.local.json` 配置的模拟账户 v1.1.15 使用：

```text
runtime_data/control/simulation/runtime_control.json
mode=SIMULATION_STRATEGY_EXECUTION_ENABLED
coordinator_mode=MONITOR_ONLY
```

该状态没有过期时间。只有以下动作会关闭本机执行：

1. 在托盘执行“锁定订单/停止策略”；
2. 删除或撤销本机模拟授权 Key；
3. 手工删除/替换本机 runtime_control.json；
4. 任一运行时安全门禁失败（交易时段、对账、Bridge、QMT、重复信号等）。

安全门禁失败只阻止当次订单，不会把持久授权自动改成 120 秒窗口。

## 启用与关闭

启用（只写本地状态，不下单）：

```powershell
py -3.12 scripts\enable_v1_1_15_simulation_execution.py
```

查看状态：

```powershell
py -3.12 scripts\bigqmt_runtime.py status --profile simulation
```

手工关闭：

```powershell
py -3.12 scripts\bigqmt_runtime.py lock-orders --profile simulation --reason "operator stopped unattended execution"
```

## “120 秒窗口”是什么意思

旧实现会在每次周期前写入 `valid_until_epoch=当前时间+120秒`，周期结束后自动锁定。这是临时授权，不符合本项目“授权后持续无人值守，直到人工关闭/删除”的要求。当前代码已改为持久 `SIMULATION_STRATEGY_EXECUTION_ENABLED`，旧接口仅作为兼容别名，不再创建临时窗口。

## 交易时段仍然保留

持久执行权限不等于全天候向券商发单。v1.1.15 仍只在 A 股交易日 09:35–14:50，并且在行情、持仓、对账和 Bridge 探活均通过时执行；非交易时段只保持待机，不会下单。
