# BigQMT 缓存清洗与验证结果（2026-09-12）

## 本轮范围

本轮只读取模拟账户 `90000001` 的 QMT 缓存，覆盖 6 个 A 股/代表 ETF 加 v1.1.17 U25 池，共 31 个标的，区间 2026-09-08 至 2026-09-11，周期 `1d`、`5m`、`1m`。没有下载、没有 Redis 写入、没有下单、没有数据湖写入。

## 清洗结果

- 统一代码为带交易所后缀的字符串。
- 统一时间为 `Asia/Shanghai` ISO 时间，并同时保留 `trade_date`。
- 统一业务键为 `code + bar_time + period + adjustment_mode`。
- `dividend_type=none` 标记为 raw 候选；未做前复权/后复权推断。
- 字段统一为 `volume_lots`、`amount_yuan`。
- 不前向填充、不把空值改成 0、不裁剪 OHLC、不覆盖原始证据。

## 验证结果

| 周期 | 清洗行数 | 结果 |
|---|---:|---|
| 1d | 124 | 通过 |
| 5m | 5,952 | 通过 |
| 1m | 29,884 | 通过 |
| 合计 | **35,960** | **CANDIDATE_VALIDATED** |

质量检查结果：0 个 RPC 错误、0 个数值错误、0 个 OHLC 关系错误、0 个负量额、0 个重复时间戳、0 个非单调时间序列、0 个分钟根数异常、0 个重大分钟与日线量额汇总不一致。记录了 247 个小额成交额舍入差异 warning（未超过 `max(1000 元, 日额×1e-5)` 门槛），没有阻断候选。

完整交易日的结构检查为：每个标的 5m=48 根、1m=241 根。分钟线成交量/成交额求和与日线一致，支持 QMT 侧暂定 `lots/元` 单位。

## 为什么仍不能入湖

“CANDIDATE_VALIDATED”只表示这批 QMT 缓存自身清洗通过，不代表数据湖发布通过。当前仍有三个独立门禁：

1. 数据湖没有 1m/5m 表结构，需先设计包含 `bar_time`、`period`、`adjustment_mode` 的独立 schema。
2. 日线重叠数据存在 raw/调整价混用，现有湖端价格口径仍为 `BLOCKED_RAW_PRICE_SCHEMA_MIX`。
3. 复权因子必须完成 PIT 可得性和公司行动链交叉验证；没有因子覆盖的候选不能进入 silver 或回测主视图。

本地机器证据：
`runtime_data/evidence/simulation/qmt_history_cache/clean_validate_candidate_20260912_141600.json`

下一步是生成“分钟线候选 schema + PIT/复权验证报告”，仍只写项目本地 evidence/candidate，不写共享数据湖。
