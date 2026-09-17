# 最新三源门禁复核（2026-09-13）

本轮只读复核使用最新隔离 Bronze candidate：

- BigQMT：`unified_v2_bronze_three_source_20260912T233000Z/source=bigqmt`
- Tushare：`unified_v2_bronze_three_source_20260912T233000Z/source=tushare`
- MiniQMT：U25 日线导出与代表性样本

## 结果

- BigQMT 最新交易日：`20260911`，新鲜度通过；
- Tushare 最新交易日：`20260911`，新鲜度通过；
- MiniQMT/BigQMT 重叠：`184/184` 行通过价格、成交量、成交额容差；
- MiniQMT/Tushare 重叠：`225/225` 行通过价格、成交量、成交额容差；
- 全套测试：`145 passed, 1 skipped`。

随后已用该 Bronze release 重建 Silver Raw candidate：
`C:/BigQMT/research/quant_data_lake/v2/silver/raw_canonical/_releases/unified_v2_silver_raw_three_source_20260913T123000Z`
（67,988 行，234 行多源验证，67,754 行 provisional，0 冲突）。

## PIT 门禁

最新门禁证据：
`runtime_data/evidence/simulation/unified_lake_v2/pit_v2_gate_latest_20260913.json`

`source_freshness=PASSED`，但以下项目仍阻断全局发布：

1. Silver 大部分行仍为单源 provisional；
2. 公司行为数值因子尚未形成完整、独立、可审计链；
3. 历史 `available_at` 尚未闭合；
4. A 股/ETF 历史 Universe PIT 尚未完成。

因此本轮仍为候选证据，不更新全局 `LATEST`，不修改旧表，不调用券商接口。
