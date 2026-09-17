# P11：只读 QMT 快照进入本地数据湖（2026-09-09）

## 数据分工

| 层 | 组件 | 职责 | 是否事实源 |
|---|---|---|---|
| 实时总线 | Redis | QMT Bridge 与本机消费者之间传递实时事件 | 否，断线可恢复 |
| 运行权威库 | SQLite WAL | 账户、持仓、委托/成交只读快照、策略 NAV、审计 | 是（当前项目） |
| 归档层 | Parquet | 按环境/日期/快照 run immutable 保存 | 分析归档 |
| 分析层 | DuckDB | 直接查询 Parquet，生成研究/报表 | 否 |
| 高频时序 | QuestDB | 暂不启用，只有 tick 量和查询需求达到阈值后再评估 | 否 |
| 研究补充 | `kitling_AI量化_review` | 研究行情/因子/策略数据，不能隐式覆盖 QMT 券商事实 | 否 |

配置见 [config/data_lake.yaml](../config/data_lake.yaml)。在 P11 阶段没有把研究湖直接提升为交易源，避免数据源过多造成口径漂移。

## 已执行导出

命令：

```text
py scripts/export_readonly_snapshot_to_lake.py --config config/host_gateway.simulation.json
```

输出目录：

`runtime_data/lake/simulation/2026-09-09/6144ca627bbb432297eb3283df9b2641/`

已生成：

- `account_assets.parquet`：1 条账户资产快照；
- `broker_positions.parquet`：5 条持仓；
- `broker_orders.parquet`：0 条委托；
- `broker_trades.parquet`：0 条成交；
- `qmt_quotes.parquet`：5 条行情快照；
- `strategy_nav.parquet`：策略独立账户 NAV 记录；
- `strategy_benchmark.parquet`：每条策略以同起点复基的 `510300.SH` 基准曲线；基准只用于比较，不表示持仓。
- `manifest.json`：源 run、环境、订单/成交数量和文件清单。

DuckDB 已直接读取上述 Parquet，计数校验为 `1 / 5 / 0 / 0 / 5 / 2`。空委托/成交表仍写入带 schema 的 Parquet，不会生成不可读取的空文件。

## 安全结论

- 导出程序只读取 SQLite WAL，不连接 QMT 或 Redis；
- `orders_enabled=false` 固定写入 manifest；
- 不导出或生成任何可执行订单意图；
- 后续 Tray 可以在只读快照成功后触发导出，但数据湖写入失败不能阻塞 QMT 只读监控。
