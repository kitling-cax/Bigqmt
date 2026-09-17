# BigQMT 增量数据湖策略（2026-09-12）

## 决定

BigQMT 是新的候选数据源，但不是全量镜像源。已由 miniQMT 或 Tushare 发布、且通过一致性校验的历史 bar 不复制；BigQMT 仅补充共享数据湖中缺失、且经过完整门禁的分区。任何差异都进入隔离候选，不覆盖历史 release。

实际共享研究数据湖为：

`C:\BigQMT\research\quant_data_lake`

`kitling_AI量化_review` 是该共享湖、DuckDB、QuestDB 使用和发布规则的审阅项目；不能把 QMT 的 `.DAT` 或 Redis 消息直接写进研究库。

## 统一字段与量纲

| 字段 | 统一口径 | BigQMT 入库条件 |
|---|---|---|
| `code` | `600519.SH` / `000001.SZ` | 保留 QMT 后缀，禁止混用 PTrade `.SS` |
| `trade_date` | Asia/Shanghai 已完成 bar 日期 | 日历校验、主键唯一 |
| `period` | `1d` / `5m` / `1m` | 与主键一同存储 |
| OHLC | 元/份（或元/股） | 正值及高低价关系通过 |
| `volume_lots` | 手 | BigQMT 必须经样本实测，未确认不得写值 |
| `amount_yuan` | 元 | BigQMT 必须经样本实测，未确认不得写值 |
| `adjustment_mode` | `none` / `front` / `back` | 原始与 PIT 研究价分层，禁止混写 |
| `available_at` | 首次可供研究的时点 | 不得早于数据真实可见时点 |
| `source_release` / `row_hash` | 不可变来源与行哈希 | 每个候选 release 必须具备 |

已知转换：Tushare 日线 `vol` 保持手、`amount` 乘 1000 转元。miniQMT 和 BigQMT 的 volume/amount 不能凭接口名称猜测；需以代表性 A 股、ETF 的共同日期实测后登记单位证据。

## 缺失优先的合并规则

| 共享湖现状 | BigQMT 与已发布值关系 | 动作 |
|---|---|---|
| 已有 miniQMT/Tushare bar | OHLC、单位、复权一致 | 仅写对账/provenance，不复制 bar |
| 缺失 bar | BigQMT 通过全部门禁 | 写入 candidate overlay，审批后发布新 release |
| 已有 bar | 任一字段有差异 | 隔离差异、保留逐行哈希，不覆盖 |
| 缓存缺失或单位未知 | 无法确认 | `BLOCKED`，不写数据库 |

## 物理流程

```text
QMT 本地缓存（保留在 F 盘）
  -> BigQMT RPC / subscribe=False
  -> _staging/<release_id>/raw_overlay Parquet
  -> 单位、OHLC、复权、PIT、日历、跨源与哈希门禁
  -> 缺失分区的不可变 Parquet release
  -> DuckDB 研究读取；QuestDB 仅写近期热数据
```

QMT `.DAT`、Redis 队列、账户快照不进入共享历史数据湖。账户和实时行情继续归 BigQMT Bridge；正式账户保持只读。

## 推进顺序

1. 建立 miniQMT/Tushare/BigQMT 的只读分区清单与最新交易日基线。
2. 对 A 股、ETF 各选择代表样本实测 BigQMT 成交量、成交额单位。
3. 生成只包含缺失业务键的 BigQMT candidate overlay 和 manifest。
4. 对每个 overlay 做逐行哈希、复权/PIT 和交易日门禁。
5. 通过后才由共享发布器生成新的 release；不得自动更新 `LATEST`。
