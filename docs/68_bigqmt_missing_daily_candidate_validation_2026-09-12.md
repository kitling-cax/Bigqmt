# BigQMT 缺失日线候选验证记录（2026-09-12）

## 目的

在任何数据湖导入前，对 BigQMT 的缺失日线候选执行只读质量、字段和单位校验。此次验证覆盖 v1.1.17 U25 无酒 ETF 池及 6 个 A 股代表标的，时间范围为 `20260820–20260911`。

## 结果

- BigQMT 返回 527 条日线；共享湖已有 292 条相同业务键；候选缺失键 235 条。
- 292 条重叠记录 OHLC 在 `1e-6` 容差内全部一致。
- 质量问题 0：无缺失 OHLC、负成交量/成交额、非数值、周末交易日或重复业务键。
- RPC/湖读取错误 0。
- BigQMT 日线成交量与共享湖成交量比值约为 1，确认单位为“手（lots）”。
- BigQMT 日线成交额与共享湖历史原始成交额比值约为 1000，确认 BigQMT 单位为“元（yuan）”，共享湖旧原始字段为“千元”；导入统一字段 `amount_yuan` 时不再转换 BigQMT，比较旧湖时才使用 ×1000。

## 复权与发布结论

- 本次只读取 `dividend_type=none` 的原始候选；没有从前复权/后复权行情反推复权因子。
- PIT/复权因子链状态为 `PENDING_PIT_FACTOR_VALIDATION`，因此结果只能标记 `CANDIDATE_ONLY`。
- 未创建 overlay，未修改共享湖，未更新 `LATEST`，未触发任何交易动作。
- 后续必须先将候选与共享湖的公司行动/复权因子链按交易日对齐并通过门禁，才能生成隔离的 candidate overlay；若缺少原始 PIT 证据则保持阻断。

## 证据

机器证据：`runtime_data/evidence/simulation/bigqmt_missing_key_scans/validated_missing_daily_20260912_114604.json`。

执行脚本：`scripts/validate_bigqmt_missing_daily_candidates.py`。
