# MiniQMT Bronze 隔离候选发布（2026-09-12）

已将模拟 QMT 内置 Python 导出的 U25 ETF 及代表性 A 股数据，按只读、源保留规则发布为隔离 Bronze candidate：

- release：`C:/BigQMT/research/quant_data_lake/v2/bronze/bars/_releases/unified_v2_bronze_miniqmt_20260912T230500Z`
- 27 个代码、64,538 行：1d 243 行、1m 53,615 行、5m 10,680 行；
- 质量门禁：业务键 0 重复、OHLC 通过、成交量/额非负、行哈希唯一；
- 单位：本批统一记录 `raw_volume_unit=lots_measured`、`raw_amount_unit=cny_measured`，依据 U25 + 000001/510300/600519 样本测量；
- 仅为 MiniQMT 来源事实，不是 canonical winner，不提供 PIT/available_at；
- `global_latest_updated=false`，旧 Bronze/Silver/PIT 未修改，正式账户仍只读，未调用订单接口。

下一步：把该 MiniQMT candidate 与 BigQMT/Tushare candidate 做业务键交集、OHLC/volume/amount 逐字段对账；任何冲突进入隔离修复队列，不能覆盖已有 release。PIT 仍须等待公司行为数值因子与精确 `available_at` 门禁。
