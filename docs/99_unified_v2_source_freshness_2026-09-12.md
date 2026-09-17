# 统一数据湖 v2 来源新鲜度门禁（2026-09-12）

命令：`scripts/check_unified_v2_freshness.py`；证据：`runtime_data/evidence/simulation/unified_lake_v2/source_freshness_20260912.json`。

- BigQMT candidate：最新交易日 2026-09-11，符合本次预期交易日，`PASSED`；
- Tushare repair candidate：最新交易日 2026-06-22，`BLOCKED_STALE_OR_UNVERIFIED`；
- 综合 freshness gate：`false`。

该门禁只记录来源是否新鲜，不会用 BigQMT 的最新数据覆盖 Tushare，也不会把旧 Tushare candidate 当成当前统一数据。新鲜度通过后仍需完成单位、公司行为、PIT 和 Universe 门禁。
