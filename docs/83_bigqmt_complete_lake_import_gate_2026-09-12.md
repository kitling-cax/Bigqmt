# BigQMT 数据湖总入库门禁（2026-09-12）

总门禁脚本：`scripts/assess_bigqmt_lake_import_gate.py`

机器证据：
`runtime_data/candidates/bigqmt_candidate_20260912_145717/final_import_gate.json`

## 明确结论

当前结论是：

```text
GO_FOR_EXPLICIT_RAW_PUBLISH_REVIEW
```

这表示 **Raw 层已经达到“可以进入正式发布审核”的状态**，并不表示已经写入湖。

已通过：

- 候选清洗和字段规范化；
- raw 导入前门禁；
- 日线和分钟线本地分区发布演练及完整回读；
- 现有湖价格冲突修复队列完整性。

仍禁止：

- 直接追加旧 `bronze/bars_raw`；
- 未经批准写入共享数据湖；
- 更新 `catalog/LATEST.json`；
- 进入 silver PIT（canonical factor chain 和 `available_at` 尚未验证）。

因此当前最准确的回答是：**可以入库审核，暂时不能直接入库执行**。只有审核隔离
canonical raw schema 并明确批准后，才可以运行独立发布器。
