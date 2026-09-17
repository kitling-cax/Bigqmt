# BigQMT PIT 数值字段对账（2026-09-12）

证据：
`runtime_data/evidence/simulation/bigqmt_missing_key_scans/pit_numeric_field_reconciliation_20260912.json`

QMT 内置文档定义的 payload 顺序为：
`[每股红利, 每股送转, 每转赠, 配股, 配股价, 是否股改, 复权系数]`。
本轮只对有独立公司行为记录的股票事件做字段级比较，绝不从价格跳变反推复权因子。

- QMT 非空事件：52 条；
- 现金/送转字段完全相等：4 条；
- Tushare 与 QMT 相等、但 Alphaforge2/Eastmoney 记录存在冲突：17 条；
- 现金字段呈现外部值约为 QMT 值 10 倍：24 条；这证明来源单位/接口口径未统一，不能自动除以 10；
- 没有独立数值记录（ETF/LOF）：7 条；
- 无法解释的事件：0 条。

结论：股票现金/送转字段已经具备“可追溯对账证据”，但尚未具备可直接写入 Silver 的统一单位合同。必须为每个来源明确单位（每股或每十股），处理 Eastmoney 与 Tushare 冲突，并补齐 ETF/LOF 的独立现金/送转字段。第 7 个累计复权系数仍需用原始行情、公司行为和时点规则独立重建；不能直接把 QMT 数值当作 PIT 因子。

本轮输出只在候选证据目录，`lake_write=false`、`LATEST` 未改变。
