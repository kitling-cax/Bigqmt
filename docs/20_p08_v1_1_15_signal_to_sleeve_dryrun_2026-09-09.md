# P08：v1.1.15 信号到策略袖套的无订单回放（2026-09-09）

## 1. 本轮范围

本轮只验证“QMT 只读行情 → v1.1.15 纯函数信号 → 模拟策略袖套候选意图”的链路。没有调用 QMT 下单、撤单、查询委托或查询成交接口；`orders_enabled=false` 保持不变。

输入基线为冻结的 `strategy_baselines/s10_d1_v1_1_15_ptrade.json`，策略袖套为：

- `S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15`
- 初始资金：100,000 元
- 已有券商持仓不自动归属该袖套，仍是 external baseline

## 2. QMT 只读信号探针

运行命令：

```text
py scripts/run_v1_1_15_signal_probe.py --adjustment front --history-start 20260801 --start 20260815 --end 20260909 --config config/host_gateway.simulation.json
```

证据：`runtime_data/evidence/simulation/qmt_v1_1_15_signal_probe_20260909_111308.json`。

结果：

- 覆盖 25 个证券、2026-08-17 至 2026-09-09 共 18 个交易日；
- 产生 11 条信号记录、2 条虚拟状态推进记录；
- 虚拟推进只用于检查状态机，不是成交、收益或回测结果；
- 1 个证券（`563230.SH`）的只读 `get_market_data_ex` 超时，探针因此标记 `ATTENTION`，不能宣称全池行情完整；
- 其余数据仍只作为研发诊断输入，QMT 复权口径尚未证明等价于 PTrade `dypre`。

代表性状态推进：

- 2026-08-18：空仓 → `511880.SS`，虚拟价格 100.707；
- 2026-09-07：`511880.SS` → `162411.SZ`，虚拟价格 1.008；
- 两者均未写入真实成交表，也未产生券商委托。

## 3. 信号到袖套候选意图

已生成候选文件：`staging/dryrun/p08_v1_1_15_signal_candidate_20260904.json`。它对应 2026-09-04 的探针候选 `162411.SZ`，仅用于检验策略资金、门禁和幂等入口。

运行：

```text
py scripts/run_dryrun_from_json.py --intent staging/dryrun/p08_v1_1_15_signal_candidate_20260904.json
```

结果：`BLOCKED`，原因是项目级 `preflight=BLOCKED`；`broker_call_made=false`，没有写入可执行订单意图。该结果符合当前安全策略：PTrade 每证券资格/评分证据仍不完整，不能把 QMT 探针直接变成模拟盘订单。

## 4. P07 重复恢复核对

在 P08 前后分别重复读取模拟与正式环境的只读快照：

- 模拟：`6144ca627bbb432297eb3283df9b2641`，相对前一快照无持仓变化，订单/成交均为 0；
- 正式只读：`eb2026868f234532a8bea3606f9ce780`，相对前一快照无持仓变化，订单/成交均为 0；
- 两个环境均保持 `orders_enabled=false`。

## 5. 结论与下一步

P08 的“只读信号生成、状态机推进、袖套候选构造、项目级拒绝”链路已跑通；P08 不能标记为交易验收通过。当前仍有两个明确限制：

1. QMT 全池存在单证券只读超时，需要交易时段或重试策略继续观察；
2. PTrade 与 QMT 的逐证券评分/资格矩阵缺失，`preflight/parity` 必须继续保持 BLOCKED。

下一步进入 P09：在不下单的前提下完善多策略袖套注册、外部基线隔离、净值/收益统计和可查询接口；同时保留本 P08 证据供后续用户明确批准时重新评估门禁。
