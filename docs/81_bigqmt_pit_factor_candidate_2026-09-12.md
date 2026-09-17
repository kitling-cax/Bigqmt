# BigQMT PIT 因子候选链（2026-09-12）

已根据 QMT `get_divid_factors` 的事件缓存生成本地 PIT 因子候选，仅用于审计，不写入数据湖。

- 候选日线：22,218 行（已排除 6,260 条上市前零填充占位行）。
- QMT 因子事件：52 个，覆盖 11 个有事件记录的标的。
- 20 个标的在探测区间没有 QMT 因子事件，可暂以“无事件候选”标记，但不能未经独立源确认直接写入 silver。
- 因子只来自 QMT 因子 payload 的事件记录；没有从前复权/后复权价格反推。
- 候选行保留 `latest_event_day`、累计因子候选值和 `available_at_status`。

当前门禁：

```text
BLOCKED_CANONICAL_PIT_AND_AVAILABLE_AT_UNVERIFIED
```

原因是：QMT 因子缓存可以形成候选链，但尚未与 miniQMT/Tushare 的公司行动链逐事件核对，且事件因子的研究可用时间 `available_at` 尚未形成独立证据。因此这一步解决了“完全没有因子候选”的问题，但不能把候选冒充正式 PIT。

本地证据：
`runtime_data/candidates/bigqmt_candidate_20260912_145717/pit_factor_candidate.json`

下一步是只读核对 52 个事件的现金分红/拆分字段、事件日和可用时间；核对通过后，才能把
22,218 行全量候选的 silver PIT 状态改为可发布评审。此前 235 行只是短区间子集。
