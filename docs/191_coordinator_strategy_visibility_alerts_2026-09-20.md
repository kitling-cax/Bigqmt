# Coordinator 策略运行可见性与重复运行告警

## 已实现

三个托盘向 Coordinator 的只读心跳现在可以携带脱敏的 `strategy_instances` 摘要：

- `strategy_id`、版本、`RUNNING/STOPPED/DEGRADED/UNKNOWN`
- 本机策略开关是否启用
- 授权 Key 状态（只报 `VALID` 等状态，不报 Key 内容）
- Bridge RPC 版本

这些字段不包含密码、Key、订单、委托、成交或信号内容，不改变本地下单门禁。

## Coordinator 接口

- `GET /api/v1/strategy-execution`：当前主机、账户、策略实例的只读投影
- `GET /api/v1/alerts`：网页告警列表
- 首页：增加“运行告警（仅网页提示，不自动停机）”区域

告警代码：

1. `ACCOUNT_AUTHORIZATION_KEY_ON_MULTIPLE_HOSTS`：同一账户多个主机存在有效 Key，仅 WARNING。
2. `DUPLICATE_STRATEGY_RUNNING_ON_MULTIPLE_HOSTS`：同一账户、同一策略在多主机 RUNNING，CRITICAL。
3. `MULTIPLE_STRATEGIES_RUNNING_ON_ACCOUNT`：同一账户同时运行多个策略，WARNING。

当前策略是“发现即网页提示”，不会自动删除 Key、降级托盘、停止策略、切换执行主机或改订单开关。处理决定仍由用户在对应托盘完成。

## 验证

- `tests/test_host_agent_snapshot.py`：验证策略摘要可上报且不含 secret/authorization_key 内容。
- 人工投影验证：两个主机上报同一账户、同一策略 RUNNING 时，接口同时返回 Key 多主机 WARNING 和重复策略 CRITICAL。
- 两个本机托盘已重新编译并启动；编译仅保留既有条件编译警告，无错误。

## 后续

1. 将 `.125`、`.113` 的托盘按同一源码版本重编译并启动。
2. 在 Coordinator 页面观察三台主机的策略实例与告警。
3. 再接入每日策略收益/成交摘要；该摘要仍走事实归档，不进入下单接口。
