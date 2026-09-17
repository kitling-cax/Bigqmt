# BigQMT 候选导入前门禁结果（2026-09-12）

针对本地候选包 `runtime_data/candidates/bigqmt_candidate_20260912_145717/`，执行了只读导入前门禁。

## 结果

- `daily_raw_overlay.parquet`：22,218 行清洗后有效候选，另有 6,260 条上市前零填充占位行已隔离。
- `intraday_raw_overlay.parquet`：35,836 行，字段完整。
- 业务键唯一：通过。
- 行哈希唯一：通过。
- 日线候选与当前 bronze 冲突数：0。
- OHLC、成交量、成交额数值检查：通过。
- 数据湖写入：未执行。
- `LATEST` 更新：未执行。

结论：

```text
raw_bronze_import_ready = true
silver_pit_import_ready = false
```

也就是说，BigQMT 原始候选已经达到“可以进入 raw bronze 发布流程”的技术就绪状态；但当前仍不能进入 silver PIT 层。silver 层还需要可审计的复权因子链、`available_at` 时点校验，以及现有湖重叠价格混用问题的独立修复。

机器证据：
`runtime_data/candidates/bigqmt_candidate_20260912_145717/import_readiness.json`

本门禁只验证候选包，不代表已经获得发布批准，也不触发任何交易行为。
