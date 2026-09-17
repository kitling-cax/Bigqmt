# BigQMT ETF/LOF 拆分字段对账（2026-09-12）

证据：
`runtime_data/evidence/simulation/bigqmt_missing_key_scans/etf_split_field_reconciliation_20260912.json`

使用 AkShare 调用 Eastmoney 基金拆分/折算历史（`fund_cf_em`）与 QMT 事件逐条比对：

- 7 条 ETF/LOF QMT 事件全部找到前一交易日的拆分/折算记录；
- 7/7 的 QMT 第 1 项（送转份额）与外部拆分比例减 1 相符；
- 7/7 的 QMT 累计复权因子与拆分比例接近，但这只是诊断关系，不能替代从 Raw 行情重建；
- 这些事件是份额拆分，不是现金分红，AkShare 分红接口的 `per_div=0` 不作为数值因子来源。

因此 ETF/LOF 的事件类型和送转比例已有独立证据，但 `available_at` 仍只有日期，且累计因子尚未经过 Raw OHLC 重建。该结果可以支持 Raw 保留原始事件记录，不能解除 Silver PIT 发布门禁。

本轮仍为只读证据，`lake_write=false`、`LATEST` 未改变。
