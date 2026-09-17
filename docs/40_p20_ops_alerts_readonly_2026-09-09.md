# P20 只读运维告警层（2026-09-09）

## 已完成

- 新增 `src/kitling_bigqmt/ops_alerts.py`，从本地状态投影计算告警。
- 新增 `scripts/check_ops_alerts.py`，可离线输出 JSON 告警结果。
- Dashboard `/api/status` 增加 `ops_alerts`；总览显示告警数量，审计页显示告警明细。

## 覆盖范围

- 订单开关意外开启：`CRITICAL`；
- QMT Bridge 不可用/断开：`CRITICAL`；
- 行情陈旧或未知：`WARNING`；
- 数据湖周期阻塞：`WARNING`；
- 活动安全阻塞（例如 510300 T+1）：`WARNING`。

## 当前验证

- Dashboard API：`alert_count=1`、最高级别 `WARNING`，对应已知的 510300 T+1 待处理状态。
- Dashboard 页面包含“运维告警”展示。
- 全量测试：`49 passed`。
- `read_only=true`、`orders_enabled=false`、`broker_call_made=false`。

告警层只读，不调用 QMT/Redis、不发送通知到外部服务、不创建或撤销委托。后续可在 P20 的备份与通知阶段增加本地托盘提示和可选的用户确认通知。
