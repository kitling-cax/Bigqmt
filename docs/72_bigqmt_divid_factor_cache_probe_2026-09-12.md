# BigQMT 复权因子缓存核验（2026-09-12）

## 实测范围

模拟账户 `90000001`，使用 `get_market_data_ex(..., dividend_type=none, subscribe=false)` 读取 31 个代表标的（6 个 A 股 + v1.1.17 U25 ETF 池）2020-01-01 至 2026-09-11 的日线，仅用 `preClose` 变化定位可能的事件日，再逐日调用只读 `get_divid_factors(code, date, date)`。没有根据价格计算因子，也没有调用下载接口。

## 结果

- 日线读取 50,344 行；定位 105 个事件日。
- 52 个事件日返回非空 QMT 因子载荷，53 个事件日为空，0 个错误。
- 茅台、平安银行、宁德时代、浦发银行、美的集团等均返回过非空因子；例如茅台 2024-06-19 返回载荷末值 `1.020716`，宁德时代 2025-08-20 返回 `1.003581`。
- 结果证明：模拟 QMT 本地缓存确实包含历史除权除息因子，之前“没有因子”的结论只针对候选日期直接查询为空，不能推导为缓存不存在。

## 接口限制

- 当前模拟桥接的区间 `get_divid_factors(start,end)` 在适配器的 DataFrame 真值判断处会报 `ValueError: truth value of a DataFrame is ambiguous`；单日接口正常。因此本次采用事件日定位后单日读取。
- 正式只读桥接当前返回 `rpc method is not allowed: get_divid_factors`，尚未暴露该读接口；这不代表正式 QMT 缓存不存在，只代表当前正式 Bridge 发布未开放该方法。

## 发布结论

因子缓存可作为 BigQMT 候选因子来源，但必须先把 QMT 原始载荷（分红、送股/配股、现金项、累计因子及事件日期）映射到统一字段，并与 miniQMT/Tushare 的公司行动链做交叉校验。候选行情仍不直接升级为 PIT；本次未创建 overlay、未写入共享湖、未更新 `LATEST`。

机器证据：`runtime_data/evidence/simulation/bigqmt_missing_key_scans/divid_factor_cache_probe_20260912_120237.json`。
执行脚本：`scripts/probe_bigqmt_divid_factor_cache.py`。
