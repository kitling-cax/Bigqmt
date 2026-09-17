# BigQMT 候选发布包就绪度（2026-09-12）

## 本地候选包

已生成本地 copy-on-write 候选发布包：

`runtime_data/candidates/bigqmt_candidate_20260912_145717/`

其中：

- `daily_raw_overlay.parquet`：22,218 条清洗后的 QMT 独有日线候选键；不包含与湖重叠的行。另有 6,260 条上市前零填充占位行已隔离，不进入候选。
- `intraday_raw_overlay.parquet`：31 个标的、4 个交易日的 1m/5m 原始候选，共 35,836 条；湖端尚无分钟线表，因此暂不声明 missing-only。
- `manifest.json`：字段、单位、行哈希、来源版本和门禁状态。
- `raw_bronze_import_plan.json`：只读入库映射与隔离表计划；不执行发布。

## 门禁结果

| 门禁 | 状态 | 解释 |
|---|---|---|
| schema/字段规范化 | PASSED | `bar_time`、`trade_date`、`period`、`adjustment_mode` 和 canonical 字段已生成 |
| 重复与行哈希 | PASSED | 候选包内无重复 hash |
| QMT 自身 OHLC/量额/时间质量 | PASSED | 0 个硬错误 |
| 日线跨源价格 | NOT_APPLICABLE | 日线包只保留湖缺失键，不覆盖重叠数据 |
| 1m/5m 跨源价格 | PENDING | 湖端目前没有分钟线数据集 |
| PIT/复权因子（silver） | BLOCKED | 尚未取得可审计的 canonical PIT factor chain |
| 现有湖重叠记录 | BLOCKED（独立修复队列） | `alphaforge2:bars_raw` 存在 raw/调整价混用，不能覆盖修复 |
| raw bronze 候选 | READY_FOR_RAW_BRONZE_REVIEW | 已达到候选评审条件，但尚未执行发布 |

## “能够入库”的准确含义

当前已经达到 **raw bronze 候选包可评审/可导入** 状态：文件可读取、字段和单位已统一、只含缺失键、没有写湖副作用。仍未达到 **silver PIT 正式发布** 状态，因为复权因子时点链和已有湖重叠价格口径尚未完全解决。

因此本轮没有写入 `C:\BigQMT\research\quant_data_lake`，没有更新 `catalog/LATEST.json`，没有产生交易调用。正式账户仍保持只读。

入库映射计划见 [文档 82](82_bigqmt_raw_bronze_import_plan_2026-09-12.md)。现有
`bronze/bars_raw` 不能直接追加，必须先采用隔离的 canonical raw schema。

下一步只需在发布前完成两项独立审核：

1. 对 22,218 条有效日线候选补齐并验证 PIT 因子来源与 `available_at`；
2. 为分钟线建立独立表后，再做 1m/5m 的跨源对账。
