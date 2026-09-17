# BigQMT 缺失日线业务键扫描（2026-09-12）

## 扫描范围

- 读取方式：BigQMT `get_market_data_ex(period=1d, dividend_type=none, subscribe=False)`。
- 范围：`2026-08-20` 至 `2026-09-11`。
- 标的：6 个 A 股代表样本（主板、创业板、科创板）和 v1.1.17 ETF 池 25 个标的，共 31 个。
- 共享湖读取：`bronze/bars_raw/year=2026/*.parquet`，DuckDB `union_by_name=true`，以 `(code, trade_date, period=1d, adjustment_mode=none)` 比较。

## 结果

| 指标 | 结果 |
|---|---:|
| BigQMT 业务键 | 527 |
| 共享湖业务键 | 292 |
| 共同业务键 | 292 |
| 缺失候选业务键 | 235 |
| 共享湖重复业务键 | 0 |
| BigQMT OHLCV 基础质量异常 | 0 |
| BigQMT RPC 读取错误 | 0 |

235 条只表示“共享湖缺少、BigQMT 有”的键，不是可发布数据。它们按日期分布为：

- ETF 池 25 个标的：`2026-09-03` 至 `2026-09-11`，每个 7 条，共 175 条。
- A 股 6 个样本：上述 7 个交易日共 42 条，另有 `2026-08-31`、`2026-09-01`、`2026-09-02` 共 18 条。

## 状态

`CANDIDATE_ONLY`。没有创建 overlay、没有写 Parquet/DuckDB/QuestDB、没有更新 `LATEST`。

下一关必须逐行复核缺失日的单位、交易日完整性和 corporate-action/PIT 链；只要任一项失败，候选保持阻断。

机器可读证据：[missing_daily_keys_20260912_112141.json](../runtime_data/evidence/simulation/bigqmt_missing_key_scans/missing_daily_keys_20260912_112141.json)
