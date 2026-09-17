# P12：模拟账户交易前预检与本地 Dry-run（2026-09-09）

## 本轮结果

用户已批准模拟账户 `90000001` 采用 QMT 独立策略风险边界；正式账户 `90000002` 仍只读。

模拟账户只读快照：

- run_id：`9018df2657e5426292535be2eae3bd70`；
- 总资产：10,040,527.34 元；
- 持仓：5 个；
- 委托：0；成交：0；
- 行情：5 个。

行情预检：

- 3 次连续采样；
- 5/5 标的每次均 `FRESH`；
- 没有超时、未知行情或空盘口阻塞；
- 证据：`runtime_data/evidence/simulation/qmt_quote_health_p12_20260909.json`。

## 本地 Dry-run

候选文件：`staging/dryrun/p12_simulation_validation_candidate.json`。

第一次运行结果：`RECORDED / PLANNED`；第二次相同 `request_id` 返回 `DUPLICATE`。两次均为：

```text
mode=LOCAL_DRYRUN_NO_QMT_RPC
orders_enabled=false
broker_call_made=false
```

本轮已验证模拟策略袖套资金、100 股整手、手续费和幂等账本，不代表已产生券商委托或成交。

## 当前剩余门禁

PTrade parity 已由用户批准的 QMT 独立风险边界替代，但 `BIGQMT_BRIDGE` 的实际订单 RPC 和运行控制仍保持关闭。下一步如要进行真实模拟验证，必须再确认：

1. 明确单笔验证订单的证券、方向、数量和价格范围；
2. 再检查模拟账户资产/持仓与行情新鲜度；
3. 通过模拟 Bridge admission 和策略袖套预算；
4. 只执行一笔最小规模验证，并等待成交回报后对账。

正式账户不会参与该流程，继续只读。
