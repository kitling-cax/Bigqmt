# 统一数据湖 v2 PIT 门禁执行结果（2026-09-12）

PIT 门禁执行器：`src/kitling_bigqmt/pit_gate_v2.py`；命令：`scripts/check_pit_v2_gate.py`。

结果为 `BLOCKED_PIT_V2`，这是预期的安全结果：

- `raw_canonical`：阻塞，当前 Silver Raw 仍为单源 provisional；
- `corporate_actions_numeric`：阻塞，累计因子没有独立验证；
- `available_at`：阻塞，历史公告时点只有日期候选；
- `universe_pit`：尚未建立；
- `source_freshness`：尚未建立；
- `manifest_hash`：通过。

证据：`runtime_data/evidence/simulation/unified_lake_v2/pit_v2_gate_20260912.json`。

门禁失败只阻止 PIT 发布，不删除或覆盖任何数据。全部条件满足后才允许生成不可变 PIT candidate，再单独评估全局研究指针切换。
