# 复权因子来源盘点（2026-09-12）

只读盘点共享湖后确认：

- `bronze/bars_raw/year=2026` 虽有 `adj_factor` 字段，但本次 31 个代表标的、2026-08-20 至 2026-09-02 的 292 条历史记录中 `adj_factor` 非空数为 0；不能把空字段当成因子证据。
- `silver/bars_pit/year=2026` 有非空 `adjustment_factor`，但覆盖的是湖中已有记录（日期最多到 2026-09-02），对此前短区间的 235 个 BigQMT 缺失候选业务键覆盖数为 0；全量 release 的 22,218 行仍需单独 PIT 审计。
- 目录中未发现独立的公司行动/分红/复权因子原始表可用于这批候选的时点关联。

因此当前缺口不是行情 OHLC 或单位，而是候选日期缺少可审计的原始 PIT/公司行动因子链。继续保持 `BLOCKED`：不得根据 BigQMT 前复权/后复权价反推，不得直接把原始 `none` 行情升级为 PIT。

证据：

- `runtime_data/evidence/simulation/bigqmt_missing_key_scans/pit_factor_coverage_20260912_115010.json`
- `docs/70_bigqmt_candidate_pit_factor_gate_2026-09-12.md`
