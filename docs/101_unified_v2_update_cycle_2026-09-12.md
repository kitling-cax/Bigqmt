# 统一数据湖 v2 更新编排器（2026-09-12）

入口：`scripts/run_unified_v2_update_cycle.py`。

每次运行固定执行：

1. 三源只读基线；
2. 来源新鲜度检查；
3. 来源保留的 Bronze candidate；
4. Silver Raw Canonical 对账 candidate；
5. PIT/公司行为/Universe 门禁。

每轮只写 `runtime_data/evidence/simulation/unified_lake_v2/` 的运行证据，不能访问 QMT/Redis、不能下单、不能修改旧湖或任何全局 `LATEST`。门禁失败时上一份批准研究 release 继续有效。

当前周期仍会因 MiniQMT 未定位、Tushare candidate 过期、Silver 仅 provisional、公司行为数值与 `available_at` 未验证以及历史 Universe 缺失而阻断全局 PIT；这些阻断原因会随每轮证据更新。
