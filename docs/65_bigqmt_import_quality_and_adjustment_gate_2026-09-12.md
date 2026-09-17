# BigQMT 导入前清洗、字段、单位与复权门禁（2026-09-12）

## 不可绕过的导入顺序

```text
只读抽取 -> 标准化清洗 -> 跨源比对 -> 单位实测 -> 复权/PIT验证
-> candidate manifest -> 人工审批 -> 新 release
```

当前模式为 `DRY_RUN_ONLY_UNTIL_ALL_GATES_PASS`。没有候选数据可以直接写入共享湖、QuestDB 或更新 `LATEST`。

## 清洗规则

1. 代码统一为 QMT `xxxxxx.SH` / `xxxxxx.SZ`，交易日统一为 Asia/Shanghai 已完成 bar 日期。
2. 数值先以 decimal 解析；空值保留为 null 和原因，禁止前向填充 OHLC、成交量或成交额。
3. 仅当标准化后的行哈希完全一致，才可合并精确重复行；同业务键但不同值一律进入 quarantine。
4. OHLC 异常、负成交量/成交额、时间重复或倒序均阻断候选 release，不做裁剪或造数修复。
5. BigQMT 的 volume/amount 在 A 股和 ETF 的 miniQMT/Tushare 共同样本量纲实测前不得发布数值。

## 复权硬边界

- BigQMT 可进入原始层的唯一价格口径是 `dividend_type=none`，并明确标为 `adjustment_mode=none`。
- BigQMT 的 `front`、`back` 只可作诊断比较，绝不作为原始行情或 PIT 因子来源。
- 复权因子和公司行动继续以共享湖既有的 canonical factor/corporate-action 链为唯一来源；不得从 BigQMT 前/后复权价格反推因子。
- PIT 价格必须在 raw candidate 通过后单独派生，并保存 `adjustment_factor`、`source_version`、`available_at`。
- 对每个发生除权、分红、拆并的证券，必须验证除权日前后窗口、因子为正、原始价到 PIT 价公式和 `available_at` 无未来泄漏。

## 发布阻断条件

任一条件失败即 `BLOCKED`：

- 字段或单位没有证据；
- `(code, trade_date, period, adjustment_mode)` 不唯一；
- 与 miniQMT/Tushare 已发布数据存在未解释差异；
- 复权因子链、除权日或 PIT 可用时间不一致；
- manifest、稳定哈希、影响范围或质量报告缺失。

通过前只产生 `_staging/<release_id>` 下的 Parquet 和报告；旧 Parquet、PIT、QuestDB 热表及 `LATEST` 均不改变。
