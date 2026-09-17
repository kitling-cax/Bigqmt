# BigQMT 1 分钟/5 分钟缓存与数据湖状态（2026-09-12）

## 结论

BigQMT 已有 1 分钟和 5 分钟历史缓存，但当前共享数据湖 `bronze/bars_raw`、`silver/bars_pit` 均没有 `period` 字段，也没有独立的 1m/5m 数据集。因此目前不能做“QMT 分钟线 vs 数据湖”的逐键差集；此前的 `28,478` 只针对日线。

## QMT 缓存读取验证

读取接口：`get_market_data_ex`，`subscribe=false`，`dividend_type=none`，只读 RPC。

| 标的 | 全历史 QMT 5m | 全历史 QMT 1m | 2026-09-08～09-11 5m | 同区间 1m |
|---|---:|---:|---:|---:|
| `600519.SH` | 77,952 | 391,384 | 192 | 964 |
| `510300.SH` | 77,952 | 391,384 | 192 | 964 |

代表性 A 股（`000001.SZ`、`300750.SZ`、`688981.SH`）和 ETF 也已通过同样的 4 日缓存结构检查；模拟账户和正式只读账户的 `600519.SH`、`510300.SH` 均通过 1m/5m 读取验证。

## 单位与完整性实测

以 2026-09-11 为例：

- 每个标的 5m 为 48 根、1m 为 241 根，时间顺序递增、无重复、OHLC 约束和非负量额检查通过。
- `600519.SH`：1m/5m 成交量求和均为日线成交量 `34,801`；成交额与日线相比分别为约 `0.999999997`、`0.999999999`。
- `510300.SH`：1m/5m 成交量求和均为日线成交量 `9,666,652`；成交额与日线相比分别为约 `0.999999998`、`0.999999999`。

据此，**QMT 分钟线当前可暂按 volume=lots、amount=amount_yuan 进入候选规范**；该结论只适用于 QMT 缓存，不能外推到数据湖（湖中尚无对应数据）。

## 入湖前新增门禁

1. 新增业务键：`code + bar_time + period(1m|5m) + adjustment_mode`，不能继续使用日线的 `trade_date` 键。
2. 时间必须保存为 Asia/Shanghai 对齐的 bar end time，并记录交易日；检查 1m 每日 241 根、5m 每日 48 根时要允许午间休市和临时停牌例外。
3. 先保留 QMT raw 版本；前复权/后复权单独分层，不能覆盖 raw。
4. 量额单位固定为 `volume_lots`、`amount_yuan`，并以“分钟求和≈日线”作为跨周期一致性门禁。
5. 与 miniQMT/Tushare 有相同键时只做逐字段对账，不重复复制；没有湖数据的 1m/5m 才能形成候选 overlay。
6. 仍需完成 PIT/复权因子和重叠 OHLC 口径校验；通过前不写入 bronze/silver，不更新 `LATEST`。

证据：
`runtime_data/evidence/simulation/qmt_history_cache/cached_history_quality_20260912_122928.json`

全程未下载、未写湖、未下单；正式账户仍是只读。

候选 schema 草案：`config/bigqmt_intraday_candidate_schema.json`，当前标记为 `DRAFT_CANDIDATE_ONLY`。
