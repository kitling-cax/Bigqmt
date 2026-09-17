# P22 策略注册与准入门（2026-09-09）

状态：`IN_PROGRESS`。已把 `kitling_AI量化_review` 的首批 ETF 策略登记为项目可审计配置，但没有因此获得订单权限。

## 当前登记

`config/strategy_registry.json` 当前包含两个独立袖套：

| 策略 | 类型 | 初始资金 | 当前准入 |
|---|---|---:|---|
| `S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15` | ETF | 100,000 | `SIMULATION_ONLY` |
| `ETF_MOMENTUM_B_SIM_MAIN_V1_1_15` | ETF | 1,000,000 | `SHADOW_ONLY` |

每条登记包含来源项目、资产类别、版本、袖套、允许账户、资金上限、信号频率和风险档案。正式账户明确禁止；`execution_enabled` 明确为 false；外部基线持仓不允许被策略自动认领。

## 校验

```powershell
py scripts\validate_strategy_registry.py
```

当前结果：2 条策略、注册表有效。自动测试已增加策略重复/正式执行拒绝覆盖，总计 `42 passed`。

## 下一步

先给每条策略补齐证券池、信号契约和停用原因，再把注册表只读投影到 Dashboard 的“策略袖套”页面。只有完成影子运行、资金预算、归属成交和用户单独批准后，策略才可能进入模拟执行；正式账户仍不允许。
