# 数据湖价格口径冲突分类（2026-09-12）

本轮将已有 bronze 记录与 QMT 同日 `none/front/back` 三种缓存逐条比对，范围为此前发现冲突的 11 个标的、2020-01-01～2026-09-11。全程只读。

## 分类结果

| 分类 | 行数 | 处理建议 |
|---|---:|---|
| MATCH_QMT_NONE | 7,419 | 可作为 raw 口径候选，但仍需保留来源和行哈希 |
| MATCH_QMT_FRONT | 231 | 不是数值错误，主要是湖端缺少/错误标注复权模式；可重分类到独立 adjusted 层，不能留在 raw |
| MATCH_MULTIPLE_MODES | 9,889 | QMT none/front 数值相同，暂标为 raw/front 等价，需按业务口径选择，不做覆盖 |
| UNMATCHED_PRICE | 233 | 无法由 QMT 三种模式解释，必须隔离；不允许自动修复 |

其中 `UNMATCHED_PRICE` 主要为：`600000.SH` 160 行、`300750.SZ` 67 行，以及 6 个 ETF 在 2020-02-25 各 1 行。`MATCH_QMT_FRONT` 的 231 行主要为 `000001.SZ` 52、`600519.SH` 79、`000333.SZ` 100。

## 修复策略

1. **不改原表**：现有 `bronze/bars_raw` 保持原样，冲突行不覆盖、不删除。
2. **可重分类部分**：精确匹配 QMT front 的 231 行，生成独立 adjusted candidate；只有在 schema 增加 `adjustment_mode=front` 后才允许发布。
3. **不可解释部分**：233 行进入 quarantine candidate，等待 miniQMT/Tushare 原始价和公司行动链核对；不能用 `adj_factor` 反推。
4. **raw 层候选**：当前全量候选 release 为 22,218 行；其中 235 行是此前短区间
   （20260820～20260911）的增量子集，不与上述重叠冲突混合。

## 当前影响

- BigQMT raw missing-only 候选仍为 `raw_bronze_import_ready=true`。
- 现有湖的 233 行未解释冲突不会阻断 missing-only 候选导入，但会阻断统一的 adjusted/PIT 发布。
- 1m/5m 湖端仍无对应表，继续保持单独 schema 评审。

机器证据：
`runtime_data/evidence/simulation/bigqmt_missing_key_scans/lake_price_schema_conflicts_20260912_143912.json`

已进一步生成逐行修复队列：
`runtime_data/evidence/simulation/bigqmt_missing_key_scans/lake_price_repair_queue_20260912.json`。
其中 231 条进入 copy-on-write 重分类候选，233 条继续隔离；9,889 条多口径匹配记录不做
自动修复，全部保留来源歧义。队列只供审核，不会原地覆盖 `bars_raw`。

本报告不执行任何湖写入或 `LATEST` 更新。
