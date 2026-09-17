# v1.1.15 PTrade 逐标诊断合同

状态：`OPTIONAL_ENHANCEMENT_ARTIFACT_GAP_RECORDED`。本文件只定义诊断输出，不改变 v1.1.15
信号、冻结、成交或资金规则，也不启用 QMT 订单。

## 当前证据缺口

现有 PTrade 长期导出只记录 RC1 的最终 `best`、`score`、当前持仓、原因和成交明细；它没有
记录每个候选标的的逐日分数、历史长度、SMA4 合格状态或被排除原因。因此，12 个 QMT 与
PTrade `best` 不同的日期不能仅凭最终日志证明是复权差异还是 PTrade 资格过滤。

已核实当前回测目录的可用产物为：UTF-16 TXT 日志、交易详情 CSV、持仓明细 CSV 和 PNG
截图。PTrade 当前界面没有可直接导出逐标矩阵的结果文件，因此 SCORE_MATRIX 诊断属于可选
增强项；缺失时项目继续使用现有产物做 artifact-only parity，但保留证据缺口，不把 QMT
研究湖数据冒充 PTrade `dypre`。

## 需要补采的最小字段

每个盘后信号日、每个 `ALL_SECURITIES` 标的写一条 JSONL 或 CSV 记录：

- `day`：信号日期；
- `security`：PTrade `.SS/.SZ` 代码；
- `history_count`：有效历史收盘数量；
- `last_close_adjusted`：PTrade `get_history(..., fq='dypre')` 的最后值；
- `momentum_score`：legacy weighted-log 分数，缺失写 `null`；
- `momentum_eligible`：是否通过 `0.05 <= score <= 2.00`；
- `sma4_value`、`sma4_pass`：4 日均线和最新值资格；
- `frozen_sessions_before`：本日排名前的冻结剩余次数；
- `excluded_reason`：如 `HISTORY不足`、`MOMENTUM_RANGE`、`FROZEN`、`INVALID_VALUE`；
- `strategy_version`、`source_run_id`、`config_hash`。

诊断记录必须在实际 PTrade 计算函数内采集，不能用 QMT 或研究湖数据代替。诊断字段可新增
日志，但不得改变候选排序、冻结递减或下单路径；运行仍可完全关闭订单。

## 回收门槛

拿到一次覆盖 12 个排名案例和 6 个分数案例的诊断输出后，主机脚本将：

1. 对照 PTrade 的 `dypre` 分数、历史长度和资格原因；
2. 区分 `PTRADE_FREEZE_EXCLUSION`、`PTRADE_DATA_OR_ELIGIBILITY` 和 `QMT_SOURCE_DIFF`；
3. 重新计算逐日 best/score parity；
4. 只有 parity、Dry-run 和账户下单前快照全部通过，才进入模拟账户 `90000001` 的受控测试。

在该输出缺失前，QMT 研究湖不能冒充 PTrade `dypre`，也不能把 QMT 原始 best 直接转为订单。
