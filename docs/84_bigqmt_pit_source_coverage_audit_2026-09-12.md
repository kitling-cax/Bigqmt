# BigQMT PIT 复权因子来源覆盖审计（2026-09-12）

机器证据：
`runtime_data/evidence/simulation/bigqmt_missing_key_scans/pit_source_coverage_20260912.json`

本审计只读取候选日线、QMT `get_divid_factors` 探针和 AF2 已有的
`corporate_action_history_eastmoney.csv`，不从调整价反推因子，也不写数据湖。

## 结果

- 候选标的：31 个；日线候选 22,218 行；QMT 因子探针覆盖 31/31。
- A 股 6 个标的中，原始公司行为表先匹配 4 个标的；后续 Tushare 补充已将 4 个未匹配事件日全部确认，逐事件达到 52/52。
- AkShare/Sina 事件日探针已覆盖 6 个 ETF/LOF 代码、7 条事件，且与 QMT 事件日 7/7 匹配；
  其余 19 个标的仍没有可确认的 ETF 专用公司行为链，不能套用股票分红表。
- 合并逐事件对账结果已更新为 QMT 52 个事件匹配 52/52；详见文档88、89。
- 所有 QMT 因子事件仍缺少可审计的历史 `available_at` 语义；当前下载时间不能冒充公告可用时间。

事件日对齐已通过，但金额/份额变化字段和历史 `available_at` 仍未闭合，因此 PIT 门禁仍为：

```text
BLOCKED_CANONICAL_FACTOR_AND_AVAILABLE_AT_UNVERIFIED
```

这不是 Raw 入库失败。Raw 候选可以在隔离 schema 下进入发布审核；只有需要复权研究价格
的 Silver 层才必须等待本门禁通过。
