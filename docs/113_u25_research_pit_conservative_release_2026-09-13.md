# U25 ETF 研究 PIT：保守版发布与指针切换

**日期**：2026-09-13  
**研究通道**：`U25_ETF_RESEARCH_PIT`  
**发布版本**：`bigqmt_etf_research_pit_20260913_145313`

## 已发布内容

- 25 个 U25 ETF/LOF，34,468 根日线；
- 7 条 ETF/LOF 份额拆分事件已由 QMT 事件载荷与独立资料核验；
- 原始日线使用 `dividend_type=none`，拆分按下一已观测交易日 09:30（上海时区）作为保守可见时点；
- 所有研究读取必须显式选定该通道、指定带时区的 `asof`，并执行 `available_at <= asof`；
- DuckDB 读取冒烟验证返回 34,468 行、25 个代码。

发布物：

`C:\BigQMT\research\quant_data_lake\silver\_bigqmt_research_pit_releases\bigqmt_etf_research_pit_20260913_145313`

## 现金分红口径

本次按 v1.1.15 的价格动量研究需求，**暂不将 ETF 现金分红写入调整因子或总收益曲线**。这并不表示 ETF 没有分红，也不把“未发现数据”解释为“零分红”。因此：

- 可用于 U25 的价格动量、回撤、因子输入和策略信号研究；
- 不可作为含息总收益、分红再投资、红利归因或跨资产绝对收益比较的权威数据；
- 若后续策略评价需要总收益，必须新增独立、可审计的基金现金分配事件源并发布新的 release，不能覆盖本版本。

## 指针切换与回滚

`LATEST_RESEARCH.json` 已以 compare-and-swap 方式从 2026-09-12 版本原子切换到本版本。旧指针保存为：

`C:\BigQMT\research\quant_data_lake\v2\catalog\history\LATEST_RESEARCH_20260913T065535980158Z.json`

新脚本 [promote_u25_research_release.py](../scripts/promote_u25_research_release.py) 仅能切换非全局研究通道；它会验证 release 清单、禁止 `GLOBAL_PIT_V2`、要求旧版本匹配、生成历史备份，并原子替换研究目录内指针。该脚本不能修改：

- `catalog/LATEST.json`；
- 旧 Silver/PIT；
- `GLOBAL_PIT_V2`；
- QMT、Redis 订单能力或账户状态。

## 仍然不发布的范围

全市场 A 股/ETF `GLOBAL_PIT_V2` 依然未发布。缺少可审计的公司行为数值、精确公告可见时间和历史证券池变更记录时，全局 PIT 门禁继续失败关闭。正式账户 `90000002` 保持只读；本次没有下单、撤单或账户写入。
