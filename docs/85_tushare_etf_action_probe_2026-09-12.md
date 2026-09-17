# Tushare ETF 公司行为探针（2026-09-12）

机器证据：
`runtime_data/evidence/simulation/bigqmt_missing_key_scans/tushare_etf_action_probe_20260912.json`

对 v1.1.17 ETF/LOF 池 25 个代码调用 Tushare `fund_div`：接口 25/25 可访问、错误 0，
但返回有分红记录的代码为 0，记录数为 0。Tushare `fund_basic` 可以识别这些 ETF，说明
不是代码格式或连接失败，而是 `fund_div` 对该 ETF 池没有可用公司行为数据。

因此 Tushare 当前只能作为“接口可用但 ETF 行动数据为空”的交叉验证证据，不能填充 PIT
因子。不得用股票 `dividend` 表替代 ETF 行动，也不得从 QMT front/back 价格反推。
Silver PIT 继续保持阻断；Raw 候选不受影响。
