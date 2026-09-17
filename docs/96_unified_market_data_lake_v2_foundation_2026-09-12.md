# 统一 ETF/A 股数据湖 v2 基础层（2026-09-12）

## 目标

在 F 盘的共享数据湖下建立一个来源保留、可审计、可发布的统一研究层，供 ETF 与 A 股共享使用。MiniQMT、Tushare 和 BigQMT 的原始记录不覆盖彼此；统一的是字段、单位、质量状态、PIT 时点和研究读取入口。

## 本次交付

- 合同：`config/unified_data_lake_v2_contract.json`；
- 初始化器：`scripts/initialize_unified_data_lake_v2.py`；
- 新目录：`C:/BigQMT/research/quant_data_lake/v2/`；
- 初始研究通道：已发布的 `U25_ETF_RESEARCH_PIT` 被显式固定为研究可读版本；
- `GLOBAL_PIT_V2` 保持 `BLOCKED_CANONICAL_ACTIONS_AND_AVAILABLE_AT`，没有全局发布指针。

初始化仅创建 v2 目录和 catalog；不导入行情、公司行为或账户事实，不改旧 `bronze`、旧 `silver` 或 `catalog/LATEST.json`，也不访问 QMT/Redis 或订单能力。

首个执行前置动作是运行 `scripts/audit_unified_lake_v2_sources.py`。它只记录三个来源的文件、字段、范围、主键和 OHLC 基线；如果 MiniQMT 数据目录未知，报告必须保留 `UNAVAILABLE_OR_UNLOCATED`，不能用 Tushare 或 BigQMT 伪装为 MiniQMT。

## 后续发布顺序

1. 分源写入 Bronze：MiniQMT、Tushare、BigQMT 各自保留 `source`、原始单位、接收时间和哈希。
2. DuckDB 进行单位、OHLC、重复键、价格冲突、新鲜度与证券分类核验。
3. 已验证记录进入 `silver/raw_canonical_v2`；冲突记录继续留在 candidate/quarantine。
4. 公司行为链完整后，由原始价独立重建 `silver/pit_v2`；所有研究行都有时区明确的 `available_at`。
5. 只有 stock raw、ETF raw、PIT、Universe、来源新鲜度、服务、manifest 七项均为 `PASSED`，才允许显式评估全局发布。

即使七项均通过，发布器仍需目录级 staging、tree hash 回读、发布锁、expected-previous-release 比较及原子 catalog 切换；本次基础层不实现也不执行该危险步骤。
