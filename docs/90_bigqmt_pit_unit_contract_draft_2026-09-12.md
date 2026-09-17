# BigQMT PIT 单位合同草案（2026-09-12）

配置：`config/bigqmt_pit_unit_contract_draft.json`

本合同把“字段含义”和“计量单位”分开锁定：Raw 保留 QMT 原值；只有在外部来源的单位元数据和逐字段对账通过后，才允许 Silver 转换。当前对账发现同一个现金字段存在精确相等、约 10 倍差异及来源冲突，不能用经验规则自动除以 10。

因此：

- QMT payload 的第 0–6 项按 BigQMT 文档记录，但第 6 项累计复权因子仍需独立重建或验证；
- 行情 Raw 的成交量统一标注为手、成交额标注为元，避免与历史湖的千元口径混用；
- Eastmoney/Alphaforge2、Tushare、AkShare 各自保留来源字段，不能在 Raw 层覆盖；
- ETF/LOF 的 AkShare 返回值目前只能作事件日证据，不能当作逐事件现金因子。

单位合同仍为草案，故 Silver/PIT 继续阻塞；Raw 隔离表不受影响。
