# AkShare/Sina ETF 公司行为探针（2026-09-12）

机器证据：
`runtime_data/evidence/simulation/bigqmt_missing_key_scans/akshare_etf_action_probe_20260912.json`

对 v1.1.17 ETF/LOF 池 25 个代码调用 `fund_etf_dividend_sina`：接口 25/25 可访问、错误 0；
其中 6 个代码返回 7 条事件记录。7 条 QMT 非空因子事件日全部与新浪事件日匹配：
`512200.SH`、`159941.SZ`、`159582.SZ`、`159995.SZ`、`159667.SZ`、`515880.SH`。

但该接口仅提供累计分红日期/金额，当前返回的 7 条记录 `per_div` 均为 0，不能证明 QMT
返回的份额变化因子，也没有公告可用时间和完整 ETF 公司行为字段。因此这一步只能解除
“事件日完全无来源”的部分疑点，不能直接生成 Silver PIT 因子。

全量 PIT 覆盖审计已将这 6 个代码标记为“事件日已对齐、数值链仍待验证”；另外 19 个
池标的仍无行动事件来源。

Raw 候选不受影响；PIT 仍需完整的 ETF 份额/分红事件、公告 `available_at` 和公式核对。
