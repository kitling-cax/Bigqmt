# Coordinator 策略运行可见性与重复运行告警规则（2026-09-20）

## 1. 核心规则

同一账户在多台机器同时存在有效授权 Key 时：

- 不自动删除 Key；
- 不自动降级账户；
- 不自动停止托盘或策略；
- 不自动阻断订单；
- Coordinator 在网页端显示告警，由用户决定是否停止某台策略。

授权 Key 表示“本机具备执行资格”，不表示 Coordinator 自动替用户做执行主机切换。

## 2. Coordinator 必须知道的运行事实

每台 Host Agent 定期上报以下非敏感信息：

```text
host_id
account_id
profile
strategy_id
strategy_version
strategy_run_state       # RUNNING / STOPPED / ERROR / UNKNOWN
strategy_policy_enabled  # true / false
authorization_key_state  # VALID / MISSING / INVALID，不上传 Key
bridge_version
last_signal_time
last_order_time
last_trade_time
heartbeat_at
```

授权 Key 只上报状态和短指纹，不上传 Key 明文。策略运行状态来自本机托盘、策略运行审计和每日证据。

## 3. 网页告警规则

### 同一账户多机有 Key

告警：`ACCOUNT_AUTHORIZATION_KEY_ON_MULTIPLE_HOSTS`

显示：账户、主机列表、Key 状态、最后心跳、当前策略，不执行自动动作。

### 同一账户同一策略多机运行

告警：`DUPLICATE_STRATEGY_RUNNING_ON_MULTIPLE_HOSTS`

触发条件：

```text
account_id 相同
strategy_id 相同
strategy_run_state = RUNNING 的 host_id 数量 >= 2
```

显示：策略版本、主机、策略开始时间、最后信号、最后订单和最后成交时间。

### 同一账户不同策略同时运行

告警：`MULTIPLE_STRATEGIES_RUNNING_ON_ACCOUNT`

这是提示性告警，不自动停止策略。网页显示每个策略的运行状态和收益归属。

## 4. Dashboard 页面

新增“策略运行监控”页面：

- 按账户查看运行主机；
- 按策略查看运行主机；
- 显示模拟/正式 profile；
- 显示 Key 状态，不显示 Key；
- 显示策略版本和运行时间；
- 显示最近信号、委托、成交和收益摘要；
- 重复运行时显示红色网页告警；
- 支持按主机、账户、策略和告警类型筛选。

Coordinator 不提供自动停止策略按钮作为第一阶段功能。停止动作仍由对应主机托盘执行。

## 5. 数据保留

Coordinator 保存：

- 主机心跳历史；
- 策略运行实例；
- 策略版本；
- 策略账户收益摘要；
- 告警产生、确认和恢复时间；
- 最后已知状态。

原始日志、订单明细和大体积行情仍保存在各主机/NAS，不直接塞入 Coordinator 主库。

## 6. 开发顺序

1. Host Agent 心跳增加策略运行摘要和 Key 状态；
2. Coordinator 增加策略运行实例表；
3. Coordinator 增加重复运行检测；
4. Dashboard 增加策略运行监控页和告警页；
5. 用 `.105/.125/.113` 三台主机回放测试；
6. 验证告警不改变任何订单开关和托盘状态。
