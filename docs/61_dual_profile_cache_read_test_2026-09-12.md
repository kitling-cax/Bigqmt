# 双账户 A 股/ETF 缓存读取测试（2026-09-12）

## 托盘重启

- simulation：`BigQMTTray.ps1` 已重启，Dashboard `17890`，Redis `6379`。
- production_readonly：`BigQMTTray.ps1` 已重启，Dashboard `17891`，Redis `6380`。
- 两端健康检查均为 `HEALTHY`；Bridge、Redis、Dashboard 通过；订单锁均为 `READ_ONLY_LOCKED`。

## 缓存读取结果

读取接口为 `get_market_data_ex`，显式使用 `subscribe=False`，时间区间为 `20260908` 至 `20260912`，字段为 time/open/high/low/close/volume/amount，未调用下载、下单或撤单。

| 账户 | 证券 | 日线 | 5 分钟 | 1 分钟 |
|---|---|---:|---:|---:|
| 模拟 `90000001` | A 股 `600519.SH` | PASSED（4） | PASSED（192） | PASSED（964） |
| 模拟 `90000001` | ETF `510300.SH` | PASSED（4） | PASSED（192） | PASSED（964） |
| 正式只读 `90000002` | A 股 `600519.SH` | PASSED（4） | PASSED（192） | PASSED（964） |
| 正式只读 `90000002` | ETF `510300.SH` | PASSED（4） | PASSED（192） | PASSED（964） |

结论：两账户均可通过 `xtquant_big_convert` 兼容的 Base64 Redis RPC 读取已下载的大 QMT 本地缓存。正式账户仍保持只读，整个测试没有产生任何交易请求。
