# QMT 本地缓存读取与 600519 验证（2026-09-12）

## 结论

本项目与大 QMT 的数据沟通继续使用 `xtquant_big_convert` Redis RPC。主机只读客户端现在对 `get_market_data_ex` 显式发送 `subscribe=False`，并使用 `xtquant_big_convert` 同款 `b64s:` 请求编码；服务端适配层透传该参数。未调用下载接口、下单接口或撤单接口。

## 版本处理

- EasyXT 原工作区保留用户未提交改动。
- 最新上游代码放在 `C:\BigQMT\work\EasyXT\EasyXT_upstream_20260912`。
- BigQMT 生产代码仍使用本项目内的 Bridge，不直接把 EasyXT 作为交易通道。

## 实测结果

| 读取路径 | 证券 | 结果 |
|---|---|---|
| Redis RPC `get_market_data_ex(subscribe=False)` | `510300.SH` 日线 | 成功，4 根 |
| Redis RPC `get_market_data_ex(subscribe=False)`（修复前） | `600519.SH` 日线/5m/1m | 超时 |
| Redis RPC `get_local_data`（修复前） | `600519.SH` 日线 | 超时 |
| Redis RPC `get_market_data_ex(subscribe=False)`（Base64 修复后） | `600519.SH` 日线/5m/1m | 成功，4/192/964 根 |
| Redis RPC `get_local_data`（Base64 修复后） | `600519.SH` 日线 | RPC 成功但返回空帧；不作为本项目主读取接口 |
| EasyXT `QMTLocalReader` 直接读 `datadir` | `600519.SH` 日线 | 成功，4 根（09-08 至 09-11） |
| EasyXT `QMTLocalReader` 直接读 `datadir` | `600519.SH` 5m/1m | 当前解析器无法识别该文件格式 |

证据文件：

`runtime_data/evidence/simulation/qmt_history_cache/cached_history_quality_20260912_090107.json`

## 判断

缓存没有失效，故障发生在缓存读取之前：大 QMT 自带的 `redis.client` 会扫描列表响应中的股票代码，并对 `600519` 等文本抛出 `DataError: Sensitive Data Detected, Forbidden!`。主机此前把原始 JSON 请求直接 `RPUSH` 到 Redis，因而包含股票代码的请求被 QMT 侧拦截；`subscribe=False` 只控制行情订阅，不会绕过这个 Redis 过滤器。`xtquant_big_convert` 已有同款 Base64 混淆协议，本项目已移植到只读客户端。修复后 Redis RPC 能正常读取已下载缓存，`600519.SH` 日线、5 分钟、1 分钟分别返回 4、192、964 根；未产生任何订单。

## 后续门禁

1. 对更多 A 股、ETF 及两账户分别执行同样的缓存质量校验。
2. 只有 Redis RPC 返回并通过 OHLCV、时间唯一性、复权一致性校验后，才允许进入数据湖。
3. 正式账户 `90000002` 继续只读；本次模拟账户也未产生任何订单。
