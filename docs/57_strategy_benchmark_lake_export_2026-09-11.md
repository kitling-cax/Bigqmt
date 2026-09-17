# 策略 NAV 与沪深 300 ETF 基准的数据湖同步

本次扩展了 F 盘只读数据湖导出，不新增任何 QMT、Redis 或订单调用。

每个 SQLite WAL 快照分区现在包含：

- `strategy_nav.parquet`：带 `strategy_id` 的独立策略净值、现金、持仓市值、收益字段；
- `strategy_benchmark.parquet`：带 `strategy_id`、`benchmark_code` 的同起点复基基准数据。

2026-09-11 的模拟盘验证分区：

`runtime_data/lake/simulation/2026-09-11/267b4bfd82fa4cff97be4f3e779db973/`

验证结果：两个文件均可由 Parquet 读取；基准记录为策略 A 的 `510300.SH`、收盘价 `4.579`、基准净值 `100,000`、收益 `0`。策略当前净值不会被基准文件覆盖，二者只在 Dashboard/DuckDB 查询层比较。

运行 `scripts/run_lake_cycle.py --profile simulation` 返回 `PASSED`，保留审计没有候选删除项，且 `orders_enabled=false`、`broker_call_made=false`。
