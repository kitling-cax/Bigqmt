# 三源 Bronze 隔离候选（2026-09-12）

已把 MiniQMT、BigQMT、Tushare（股票 `daily` + ETF `fund_daily`）合并为源保留的隔离 candidate：

- release：[unified_v2_bronze_three_source_20260912T233000Z](C:/BigQMT/research/quant_data_lake/v2/bronze/bars/_releases/unified_v2_bronze_three_source_20260912T233000Z)
- 总计 68,397 行：BigQMT 58,054、Tushare 10,100、MiniQMT 243；
- 三个来源分别通过唯一键、OHLC、非负数量和行哈希门禁；
- MiniQMT/BigQMT 在 193 个重叠日键上全部通过；MiniQMT/Tushare 在 U25 ETF 225 个键及代表股票 18 个键上通过价格、成交量和成交额容差；
- Tushare ETF 通过 `fund_daily` 补齐，`daily` 接口本身不返回 ETF；
- 该 release 仍是 Bronze 事实层，不选择 canonical winner，不包含 PIT/`available_at`；全局 `catalog/LATEST` 未修改。

下一步是对三源候选做 Silver canonical 选择和冲突分类，再补齐公司行为数值因子、精确可用时间及历史 Universe PIT。任何门禁未通过都只产生新隔离 release，不覆盖现有版本。
