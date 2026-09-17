# BigQMT 候选 PIT/复权因子门禁（2026-09-12）

## 检查范围

对上一阶段验证得到的 235 个缺失候选业务键，读取共享湖 `silver/bars_pit/year=YYYY`（DuckDB `union_by_name=true`），按 `code + trade_date + period=1d + adjustment_mode=none` 对齐，并要求 `adjustment_factor` 非空。

## 结果

- 候选键：235
- PIT 覆盖候选键：0
- 非空复权因子：0
- 状态：`BLOCKED`

当前共享湖 PIT 表在这组标的/日期上没有可直接关联的因子证据（现有 PIT 数据覆盖到 2026-09-02，但主要是湖中已存在的 ETF 记录；缺失候选没有对应键）。不能用 BigQMT 前复权/后复权行情倒推因子，也不能把 `none` 原始价直接冒充 PIT 价。

## 发布影响

候选仍保持 `CANDIDATE_ONLY`，不得创建 overlay、写入共享湖或更新 `LATEST`。需要先取得同口径原始公司行动/复权因子链，完成 PIT 可用性和时点（`available_at`）校验，再进入候选发布门禁。

机器证据：`runtime_data/evidence/simulation/bigqmt_missing_key_scans/pit_factor_coverage_20260912_115010.json`。
执行脚本：`scripts/check_bigqmt_candidate_pit_coverage.py`。
