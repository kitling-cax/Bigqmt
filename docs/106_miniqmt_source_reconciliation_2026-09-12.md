# MiniQMT 与 BigQMT/Tushare 对账（2026-09-12）

使用 `scripts/fetch_tushare_overlap_candidate.py` 刷新 Tushare 候选，再用 `scripts/reconcile_miniqmt_sources_v2.py` 对 MiniQMT 日线候选进行只读业务键对账：

- MiniQMT：去重后 252 行、27 个代码（U25 + 510300/600519/000001）；
- BigQMT：共有 193 个 `(code, trade_date)` 重叠键，OHLC、volume、amount 全部在容差内一致（193/193）；
- Tushare：实际刷新到 2026-09-11，返回 000001.SZ 与 600519.SH 共 18 行；18/18 重叠键通过价格 1e-6、成交量 1 手、成交额 200 元容差。ETF 在 `daily` 接口无返回，不能据此宣称 ETF 三源一致。
- 未修改任何既有 Bronze/Silver/PIT，未更新全局 `LATEST`。

结论：MiniQMT/BigQMT 同区间日线已通过；股票代表样本的 Tushare 三源对账已通过，ETF 仍需可用的 Tushare/其他独立 ETF 日线源。PIT 数值因子与 `available_at` 门禁仍独立阻塞全局 Silver/PIT。
