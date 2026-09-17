# Silver bar_time 键修复与三源候选重建（2026-09-12）

修复了 Silver canonical builder 将同一交易日多根 1m/5m K 线误聚合的问题：

- 日线使用 `(code, trade_date, frequency, asset_class)`，跨来源时间戳统一为交易日；
- 分钟线使用规范化 UTC `bar_time`，保留每根 K 线唯一身份；
- 混合 CSV/Parquet 时间类型先统一，避免整数时间戳与 pandas `Timestamp` 排序异常；
- Tushare fractional lots 与 QMT 元取整金额采用显式小额容差（0.5 手、2 元），不做隐式倍数转换。

重建隔离 Silver candidate：

- release：[unified_v2_silver_raw_three_source_20260913T010000Z](C:/BigQMT/research/quant_data_lake/v2/silver/raw_canonical/_releases/unified_v2_silver_raw_three_source_20260913T010000Z)
- 67,988 行、55 个代码；`VERIFIED_MULTI_SOURCE=234`、`PROVISIONAL_SINGLE_SOURCE=67,754`；冲突为 0；
- `global_publishable=false`，因为大部分历史/分钟数据仍缺多源确认，PIT/available_at 也未建立；
- 旧 Silver、PIT 和 `catalog/LATEST` 均未修改。
