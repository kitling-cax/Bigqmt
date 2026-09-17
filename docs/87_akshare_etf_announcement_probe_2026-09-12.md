# AkShare/Eastmoney ETF 公告可用时间探针（2026-09-12）

机器证据：
`runtime_data/evidence/simulation/bigqmt_missing_key_scans/akshare_etf_announcement_probe_20260912.json`

对 v1.1.17 ETF/LOF 池 25 个代码调用 `fund_announcement_dividend_em`：

- 25/25 请求完成，真实接口错误 0；
- 11 个代码返回 24 条公告记录；
- 14 个代码返回合法空结果；
- 发现的公告包含公告日期和公告 ID，可作为后续 `available_at` 的原始证据，但只有日期，
  还必须按交易日历映射到可用时刻。

此前 AkShare 空结果触发的 `Length mismatch` 已在探针脚本中修复，不再误报为接口错误。
公告存在不等于复权因子已验证：仍需公告中的份额/分红数值与 QMT 因子逐事件核对。
本探针不写数据湖、不更新 `LATEST`。
