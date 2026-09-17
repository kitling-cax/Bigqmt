# Tushare ETF/LOF 公司行为补充探针（2026-09-13）

对 v1.1.17 U25 的 25 个 ETF/LOF 逐代码只读调用 Tushare `fund_div`，结果为 0 行。该结果不能解释为“没有分红”，只能说明当前接口/代码覆盖没有返回可用分红事件。

证据：

`runtime_data/staging/actions/tushare_fund_div_u25_20260913.parquet`

清单：

`runtime_data/staging/actions/tushare_fund_div_u25_20260913.manifest.json`

因此没有把 `fund_adj` 累计因子或空结果写入 PIT。ETF/LOF 公司行为仍需独立公告/交易所来源，且必须补齐精确 `available_at` 与 Raw→PIT 因子重建后，才能解除全局 PIT 门禁。
