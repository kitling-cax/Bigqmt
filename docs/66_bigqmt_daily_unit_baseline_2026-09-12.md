# BigQMT 日线字段与单位只读基线（2026-09-12）

## 范围与安全性

- 只读读取 BigQMT 模拟 Bridge：`get_market_data_ex(period=1d, dividend_type=none, subscribe=False)`。
- 只读读取共享湖 `C:\BigQMT\research\quant_data_lake\bronze\bars_raw\year=2026`，读取时使用 `union_by_name=true`，不改旧 Parquet。
- 未下载数据、未写 QuestDB/DuckDB/Parquet、未更新 `LATEST`、未调用下单或撤单。

## 共同样本

区间：`2026-08-20` 至 `2026-09-02`。BigQMT 与共享湖的共同交易日共 48 行。

| 标的类别 | 代码 | 共同日数 | OHLC 最大差 | BigQMT volume / 湖 volume 中位数 | BigQMT amount / 湖 amount 中位数 |
|---|---:|---:|---:|---:|---:|
| 主板 | `600519.SH` | 7 | 0 | 0.999993 | 1000.000000 |
| 主板 | `000001.SZ` | 7 | 0 | 1.000000 | 1000.000000 |
| 创业板 | `300750.SZ` | 7 | 0 | 1.000000 | 1000.000000 |
| 科创板 | `688981.SH` | 7 | 0 | 1.000000 | 1000.000000 |
| ETF | `518880.SH` | 10 | 0 | 1.000000 | 1000.000000 |
| LOF | `160723.SZ` | 10 | 0 | 1.000000 | 999.999999 |

## 结论（仅限 BigQMT 日线）

1. BigQMT `open/high/low/close` 与共享湖共同样本完全一致。
2. BigQMT `volume` 与共享湖现有 `volume` 为同一量级，可按“手”标准化；少量小数差异来自共享湖上游精度，不是量纲差。
3. BigQMT `amount` 为元；共享湖旧 `bars_raw.amount` 在上述样本为千元。因此 BigQMT 候选行进入统一字段 `amount_yuan` 时直接使用 BigQMT amount；与共享湖旧 raw 对账时使用 `lake.amount * 1000`。
4. 此证据不外推到 `5m`、`1m`。分钟线 volume/amount 继续 `UNKNOWN_UNTIL_SEPARATE_MEASUREMENT`，不得发布。

## 发现的既有读取风险

同一年度的旧 `bars_raw` Parquet 存在列集合不一致（部分文件缺 `amount`）。只读审计必须使用 `DuckDB read_parquet(..., union_by_name=true)`；候选发布前还须通过现有共享 `quant_research_core` 的 schema contract，不能以旧分区的偶然 schema 为新标准。
