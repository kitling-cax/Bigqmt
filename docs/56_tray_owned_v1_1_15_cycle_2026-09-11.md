# Tray 所有的 v1.1.15 模拟执行循环

状态：`AUTOMATION_CORE_READY / EXECUTION_NOT_SCHEDULED`。

## 已实现

`scripts/run_v1_1_15_simulation_cycle.py` 是模拟盘 `90000001` 唯一的循环执行器：

1. 读取已持久化的收盘信号；
2. 在下一个交易日、`09:35–14:50` 的有限窗口内读取 Bridge、账户、委托、持仓、行情与策略袖套；
3. 强制 `外部基线 + 策略袖套 = 券商持仓`；有未完成委托、行情/账户异常或 T+1 可用数量不足即阻断；
4. 每次至多构造一笔操作；切换时严格先卖，卖出完成并对账后下一轮才可能买入；
5. 用 `signal_day + side + code + quantity` 构造稳定的幂等信号 ID，并在 SQLite WAL 中先写入 `strategy_execution_attempts`；
6. 仅当 Tray 请求 `--execute` 时才短时解锁模拟 Bridge，收到响应或超时后立即恢复锁单；超时写为 `UNKNOWN_TIMEOUT`，禁止自动重试。

首次真实成交仍由每日记录和后续 Bridge 成交事实归属到策略袖套；循环本身不把委托响应假定为成交。

## 托盘入口

模拟盘托盘已新增：

- `Preflight v1.1.15 next-session cycle (no orders)`：只做下一个执行循环的实时预检；
- `Execute one preflighted v1.1.15 simulation action`：模拟盘限定的一次性执行入口，弹出确认后仍须通过上述全部门禁。

正式盘托盘没有这些入口，也不启动策略执行循环。

## 本轮验证

- 单元测试：`70 passed`；
- PowerShell 托盘脚本语法：通过；
- 2026-09-11 20:03（收盘后）本机预检：按预期 `outside bounded simulation execution window` 阻断；`broker_call_made=false`、订单锁仍关闭；
- 重启后的模拟盘托盘健康：`HEALTHY`，Redis、Bridge 快照、Dashboard 与订单锁全部通过。

## 下一交易时段

先从托盘运行一次无订单预检，取得交易时段的行情/账户/策略归属对账证据。预检通过后，操作员可从同一托盘的一次性执行入口启动一笔模拟盘动作；不启用无人值守的批量下单，直至首个完整“信号—委托—成交归属—收盘 NAV”循环完成复核。
