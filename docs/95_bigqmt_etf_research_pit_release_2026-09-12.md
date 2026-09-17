# BigQMT U25 ETF 独立研究 PIT 发布验证（2026-09-12）

## 结论

`bigqmt_etf_research_pit_20260912_175315` 已作为**隔离的研究数据发布**。它可为 v1.1.17 U25 无酒 ETF 池提供可复现的日频动量、净值曲线和最大回撤研究输入；不替代共享数据湖的全局 `silver/bars_pit`，不更新 `catalog/LATEST.json`，也不产生任何交易信号或订单。

## 发布范围

| 项目 | 已验证结果 |
| --- | --- |
| 标的范围 | v1.1.17 U25 ETF 池，25 个 ETF/LOF |
| 日线行数 | 34,468 |
| 原始价格 | BigQMT `get_market_data_ex`，`dividend_type=none` |
| 公司行动 | 7 个 ETF 拆分事件，QMT payload 与 Eastmoney/AkShare 拆分比例逐项对账 |
| 研究复权 | `FORWARD_SPLIT_ONLY_CONSERVATIVE_PIT_V1` |
| PIT 时点 | 公告日/事件日之后的下一个已观察交易日 09:30（Asia/Shanghai） |
| 发布位置 | `C:/BigQMT/research/quant_data_lake/silver/_bigqmt_research_pit_releases/bigqmt_etf_research_pit_20260912_175315` |

发布 manifest：

`C:/BigQMT/research/quant_data_lake/silver/_bigqmt_research_pit_releases/bigqmt_etf_research_pit_20260912_175315/publish_manifest.json`

树哈希：`13df585a14c2669fd2ddae7e76c8ec86f152da7d9bdbe5221e7f105da326589a`。

## PIT 查询与研究探针

已运行只读探针：

```powershell
$env:PYTHONPATH='src'
py scripts\probe_bigqmt_etf_research_pit.py
```

证据：`runtime_data/evidence/simulation/research_pit_probes/etf_research_pit_probe_20260912_180122.json`。

探针按 `available_at <= 2026-09-11T15:30:00+08:00` 过滤，再对每个标的读取最后 26 个交易日，生成：

- 25 日 trailing return；
- 同一区间 maximum drawdown；
- 每个输入窗口最后一条可用时间。

结果为 25 个标的、25 条研究输入。该脚本不进行 QMT/Redis 调用，不写数据湖、不写 `LATEST`，且订单能力恒为关闭。

## 研究使用契约

1. 回测或因子脚本必须在每个研究时点过滤 `available_at <= asof`；不得按今天的数据修订过去的可见集合。
2. `open/high/low/close` 是经已验证 ETF 拆分前向调整后的研究价格。`*_raw` 字段保留原始 BigQMT 价格；两者不可混用。
3. 此 release 仅覆盖 U25、仅覆盖已验证拆分链。它没有声称覆盖 A 股现金分红、全部 ETF 现金分配或精确交易所公告时间。
4. 因子研究与回测可以基于该研究数据启动，但具体策略结论仍必须另行锁定标的池、频率、资金/容量、回测区间及成本、杠杆/做空约束，并经过质量门。

## 未改变的安全边界

- 旧 `bronze/bars_raw`：未修改。
- 旧 `silver/bars_pit`：未修改。
- 全局 `catalog/LATEST.json`：未修改。
- 正式账户 `90000002`：继续只读。
- 本次未发生券商调用、Redis 写入、下单或撤单。

全局 PIT 阻塞仍然有效：A 股现金公司行为单位冲突、非 U25 ETF 的完整行动链及精确 `available_at` 证据尚未补齐。因此该研究 release 是一个明确隔离的研究层，不是全局数据切换。
