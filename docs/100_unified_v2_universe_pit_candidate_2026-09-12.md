# 统一数据湖 v2 Universe PIT candidate（2026-09-12）

已按 v1.1.17 U25 配置生成隔离 Universe candidate：

`C:/BigQMT/research/quant_data_lake/v2/silver/universe_pit_v2/_releases/unified_v2_universe_20260912T144500Z`

共 25 个 ETF，主键和行哈希通过，`available_at` 时区完整。为防止当前证券池倒灌历史，成员关系只从显式 `effective_from=20260912` 起生效，状态为 `FORWARD_ONLY_CANDIDATE_NOT_HISTORICAL`，不能作为历史回测 Universe，也不能解除全局 PIT 门禁。

下一步需要导入带生效日和可见时点的历史证券池变更记录，分别覆盖 A 股与 ETF/LOF；没有证据的历史成员关系必须保持缺失或候选状态。
