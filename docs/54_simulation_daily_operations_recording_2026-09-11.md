# 模拟账户每日运行记录

自 2026-09-11 起，模拟账户 `90000001` 的 v1.1.15 策略每日运行记录由两层独立机制保存。

1. **BigQMT Tray 本机记录**：模拟盘托盘每日 16:20 运行
   `scripts/record_v1_1_15_simulation_daily.py`，读取 QMT Bridge、策略袖套、账户、委托、成交与订单锁；输出到
   `runtime_data/evidence/simulation/daily_operations/`。它不包含订单、撤单或放开权限的代码。
2. **本聊天日报跟进**：同一时间核对项目的日常证据、信号和状态进度；无异常时不打扰，有异常或需要操作时提示。

日报固定核验：

- QMT Bridge/Redis/托盘健康与运行时订单锁；
- 最新完整收盘信号及其来源；
- 策略袖套现金、归属持仓、净值、收益；
- 策略净值基准：沪深 300 ETF `510300.SH` 的收盘价、同起点复基净值与超额收益；
- 券商委托与成交事实；
- `外部基线 + 策略归属 = 券商总持仓` 对账；
- 正式账户 `90000002` 持续不参与策略执行。

首份记录：`runtime_data/evidence/simulation/daily_operations/v1_1_15_daily_20260911_103024.json`，状态为 `PASSED`。

收盘口径固定为同日 `daily_YYYYMMDD_close`；同一日重试复用该幂等标识，不会重复写入净值或基准点。
