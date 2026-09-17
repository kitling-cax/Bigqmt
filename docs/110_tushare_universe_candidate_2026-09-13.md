# Tushare 历史 Universe 原始候选（2026-09-13）

已对 Tushare `stock_basic`（L/D/P）和 `fund_basic(market=E)`（L/D/I）做只读抓取，并生成隔离 staging：

`runtime_data/staging/universe/tushare_universe_candidate_20260913.parquet`

结果：

- 8,687 条成员区间候选、8,687 个代码；
- A 股 5,901 个；ETF/交易所基金 2,786 个；
- 0 个股票缺少 `list_date`；106 个基金因缺少 `list_date` 被隔离；
- 主键、行哈希、时区字段校验通过。

## 重要限制

这是 Tushare 当前快照，不是历史时点快照。候选行的 `available_at` 明确标记为 `SNAPSHOT_ONLY`，不能用于历史 PIT；基金部分仍有上市日期缺口，也不能用首次行情日期冒充上市日期。

因此该文件只作为后续历史证券池重建的原始证据，不发布到 `silver/universe_pit_v2`，不更新全局 `LATEST`。

下一步需要补充带历史可见时间的交易所/公告/证券池变更证据，并为退市事件生成独立的 bitemporal 版本，才能解除 Universe PIT 门禁。
