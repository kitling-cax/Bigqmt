# BigQMT PIT 事件逐行对账（2026-09-12）

机器证据：
`runtime_data/evidence/simulation/bigqmt_missing_key_scans/pit_event_reconciliation_20260912.json`

本轮将 52 个 QMT 非空复权事件逐一与股票公司行为表、Tushare 股票公司行为及 AkShare ETF 事件日比对：

- 事件日匹配：52/52；此前 4 个未匹配事件已由 Tushare 补充确认（600519.SH：20221227、20231220；300750.SZ：20250124、20260810）；
- 52/52 事件均能找到公告日期候选，但只有日期，没有公告时刻；
- 独立数值因子核对：尚未通过。

所以本轮只证明了事件日期可追溯，不能把 QMT payload 的份额/复权因子直接发布到
Silver。当前 `available_at` 仍是 `DATE_ONLY` 候选，需要按交易日历和公告时刻映射；数值
字段还要取得独立来源后再核对。已生成 52 行本地 PIT 事件候选包，仅供审核；Raw 入库审核不受影响，数据湖没有写入。
