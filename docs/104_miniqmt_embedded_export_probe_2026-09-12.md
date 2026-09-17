# MiniQMT 内置 Python 导出验证（2026-09-12）

## 范围

在模拟 QMT 内置 Python 3.6.8 中运行 `deploy/miniqmt/export_miniqmt_bars_v2.py`，
仅调用 `xtquant.xtdata.get_market_data_ex`，不导入 `xttrader`，不调用下单/撤单，也不写入数据湖。

## 实测结果

- 目标代码：`510300.SH`、`600519.SH`；周期：`1d`；区间：2026-09-01 至 2026-09-12。
- 导出文件：`runtime_data/evidence/simulation/miniqmt_exports/probe_20260912_2255.csv`。
- 首次缓存读取时 `600519.SH` 返回 9 行，`510300.SH` 返回 0 行；随后在同一内置运行时调用只读 `xtdata.download_history_data` 刷新 1d/1m/5m，再次导出成功。
- 刷新后日线：两个代码各 9 行（2026-09-01 至 2026-09-11）；1 分钟各 2,169 行，5 分钟各 432 行。
- 分钟/5 分钟成交量求和与日线完全一致，成交额差异仅为浮点舍入（最大 145 元），见 `runtime_data/evidence/simulation/miniqmt_exports/intraday_reconcile_20260912.json`。
- 单位抽样复核由 `scripts/measure_miniqmt_units.py` 完成：`510300.SH`、`600519.SH`、`000001.SZ` 的成交额÷收盘价与成交量之比为 99.54–99.94，故本次构建日线/分钟 `volume` 记为 `lots_measured`（手），成交额记为 `cny_measured`（元）。该结论覆盖当前 3 个代表标的，不替代后续更大样本门禁。

## 主机侧验证

使用 `scripts/validate_miniqmt_export_v2.py` 分别对 ETF 与股票日线完成规范化与 Bronze 质量检查：各 9 行、0 重复键、OHLC/非负数量/行哈希全部通过，状态 `CANDIDATE_VALIDATED`。

单位若传入 `UNVERIFIED` 会返回 `BLOCKED_VALIDATION`（退出码 2），因此不会静默导入。

## 后续动作

1. 对更多 ETF/A 股代表标的重复单位测量，形成按资产类别的单位合同；
2. 形成 MiniQMT Bronze candidate，与 BigQMT/Tushare 做业务键及字段对账；
3. 在 PIT 数值因子和 `available_at` 门禁通过前，不发布全局 Silver/PIT、不更新 `catalog/LATEST`。

安全结论：本次 `lake_write=false`、`global_latest_updated=false`、`orders_enabled=false`、`broker_calls=false`。
