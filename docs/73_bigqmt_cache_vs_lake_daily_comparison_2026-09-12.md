# BigQMT 缓存与数据湖日线对比（2026-09-12）

## 对比口径

模拟账户 `90000001` 的 BigQMT `get_market_data_ex(dividend_type=none, subscribe=false)`，与共享湖 `bronze/bars_raw`，31 个标的（6 个 A 股 + v1.1.17 U25 ETF 池），日期范围 2020-01-01 至 2026-09-11。业务键为 `code + trade_date + period=1d + adjustment_mode=none`。全程只读。

## 覆盖关系

| 项目 | 数量 |
|---|---:|
| QMT 缓存行 | 50,344 |
| 数据湖 bronze 行 | 21,866 |
| 两边重叠 | 21,866 |
| QMT 有、湖没有 | 28,478 |
| 湖有、QMT 没有 | 0 |

说明：现有湖记录是 QMT 缓存的子集。28,478 行差集已经拆分为：湖起始日之前 28,237 行、湖结束日之后 235 行、湖区间内部缺口 6 行。不能据此把湖缺失行直接追加，因为价格口径还存在下面的异常。详见 `docs/74_qmt_only_breakdown_and_cleaning_plan_2026-09-12.md`。

## 单位

- 成交量：中位比值 QMT/湖 = `1.0`，两边均为手（lots）。
- 成交额：中位比值 QMT/湖 ≈ `999.9999`，QMT 为元，湖历史字段为千元；统一字段 `amount_yuan` 时湖值需 ×1000，QMT 不转换。

## 价格口径异常

- 21,866 条重叠记录中，1,838 个 OHLC 字段不一致，涉及 464 个业务键、11 个标的。
- 主要区间：`000001.SZ`（2020-11-23 至 2026-06-11）、`000333.SZ`（2020-11-23 至 2024-12-31）、`300750.SZ`（2022-11-30 至 2024-12-31）、`600000.SH`（2021-11-01 至 2024-12-31）、`600519.SH`（2021-11-29 至 2026-06-25）。
- 典型样本：2020-11-23 `000001.SZ`，QMT close=19.62，湖 close=17.004；成交量/成交额相同，但 OHLC 出现现金调整后的差异。湖中还带有 `adj_factor`，但部分行价格表现为加减现金调整、部分行接近 raw，不能统一按该字段乘除还原。
- 另有 2020-02-25 的少量 ETF 小数差异，需要独立确认精度/复权来源。

结论：湖 `alphaforge2:bars_raw` 实际混合了 raw 与调整后价格，表名和 `adjustment_mode=none` 不可信。此次比较状态为 `BLOCKED_RAW_PRICE_SCHEMA_MIX`；不能覆盖或把 BigQMT 行直接发布到 bronze/silver。

## 证据与后续

机器证据：`runtime_data/evidence/simulation/bigqmt_missing_key_scans/cache_vs_lake_daily_20260912_122156.json`。
执行脚本：`scripts/compare_bigqmt_cache_to_lake.py`。

后续先建立“raw/调整价分层”的清洗规则，并用 QMT 因子事件、miniQMT/Tushare 原始公司行动链交叉验证；通过后只能以 copy-on-write candidate overlay 发布，不能修改现有 `LATEST`。
