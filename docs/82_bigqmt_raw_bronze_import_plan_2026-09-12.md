# BigQMT 原始层入库映射计划（2026-09-12）

## 本轮产物

针对候选发布包
`runtime_data/candidates/bigqmt_candidate_20260912_145717/`，已生成只读入库映射计划：

`runtime_data/candidates/bigqmt_candidate_20260912_145717/raw_bronze_import_plan.json`

该文件只描述“未来如何发布”，不会创建数据湖目录、写入 Parquet、修改 DuckDB 或更新
`catalog/LATEST.json`。

目标字段和分区的机器可读定义位于
`config/bigqmt_raw_overlay_schema.json`，当前仍是 `DRAFT_ISOLATED_RAW_ONLY`。

发布流程已在本地演练并回读校验：
`runtime_data/publish_dryrun/bigqmt_candidate_20260912_145717/`。日线 22,218 行、分钟线
35,836 行均按计划分区写出后完整读回；这不是共享湖发布。
演练目录采用幂等复用策略，重复执行不会删除旧产物；若 release 内容冲突则直接停止。

## 为什么不能直接追加现有 `bronze/bars_raw`

现有 `bars_raw` 是历史日线表，主键只有 `code + trade_date`，且不同分区的字段并不完整；
它没有稳定承载 `period`、`adjustment_mode`、`source_release`、`available_at` 和明确的
`amount_yuan` 单位。直接追加会丢失来源血缘，并可能再次把 raw 与调整价混在一起。

因此计划中的目标是两个隔离的 canonical raw 表：

- `bronze/bigqmt_raw_overlay`：日线，按 `year/period` 分区；
- `bronze/bigqmt_intraday_raw_overlay`：1m/5m，按 `year/month/period` 分区。

两者均使用 `code + bar_time + period + adjustment_mode` 业务键，保留完整 canonical
字段。`volume_lots` 和 `amount_yuan` 不在发布过程中静默换算。

## 门禁结论

| 项目 | 结果 |
|---|---|
| 候选包字段与行哈希 | PASSED |
| 日线有效缺失候选 | 22,218 行 |
| 分钟线候选 | 35,836 行（1m/5m） |
| 上市前零填充占位 | 6,260 行，已隔离，不入候选 |
| 候选与当前湖有效键冲突 | 0 |
| 现有 `bars_raw` 直接追加 | BLOCKED，必须先建隔离 schema |
| raw 发布批准 | PENDING_EXPLICIT_REVIEW |
| silver PIT 发布 | BLOCKED，等待 canonical factor chain 与 `available_at` |

下一步是对该计划进行人工审核；审核通过后还需单独编写“显式批准才可执行”的发布器。
在此之前，不得把候选文件复制到共享数据湖，也不得更新 `LATEST`。
