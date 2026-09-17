# 统一数据湖 v2 首个 Bronze candidate 与研究读取器（2026-09-12）

## 已执行

- BigQMT 与 Tushare 已标准化为来源保留的 v2 Bronze schema，共 32,093 行；
- 发布位置：`C:/BigQMT/research/quant_data_lake/v2/bronze/bars/_releases/unified_v2_bronze_20260912T141745Z`；
- 两个来源分别通过主键、OHLC、非负数量和行哈希检查；
- `silver_pit_ready=false`，该 candidate 不是统一研究价格，也不更新任何 LATEST。
- 导入实现：`src/kitling_bigqmt/lake_ingest_v2.py`；它保留 Tushare 的千元成交额原值与单位，不把来源事实静默转换成研究价格。

## 读取方式

`src/kitling_bigqmt/research_loader_v2.py` 提供 release-aware loader 和 DuckDB 查询封装。每次研究必须选择 channel/release_id、使用带时区的 `asof`，由读取器先过滤 `available_at <= asof`，再交给 DuckDB 进行因子和回测查询。Redis、SQLite 和 QuestDB 不会被研究读取器当作历史权威源。

当前可用 channel 仍是 U25 隔离 ETF PIT；`GLOBAL_PIT_V2` 没有 approved release，读取会 fail-closed。

公司行为证据也已发布为 v2 隔离 Bronze candidate：`C:/BigQMT/research/quant_data_lake/v2/bronze/corporate_actions/_releases/unified_v2_actions_20260912T143500Z`，52 条事件日期 52/52 对齐，但累计因子和 `available_at` 仍明确阻断。

## 下一步

Silver Raw Canonical candidate 已实际生成：`C:/BigQMT/research/quant_data_lake/v2/silver/raw_canonical/_releases/unified_v2_silver_raw_20260912T142500Z`。当前 32,093 行 / 54 代码全部为 `PROVISIONAL_SINGLE_SOURCE`，验证交集为 0；这是因为本轮 BigQMT 与 Tushare 候选的业务键范围没有重叠，不能假称多源确认。下一步由公司行为 v2 和 Universe PIT 生成全局 PIT candidate；MiniQMT 目录定位及单位实测完成前，不将两源 candidate 冒充三源正式数据。
