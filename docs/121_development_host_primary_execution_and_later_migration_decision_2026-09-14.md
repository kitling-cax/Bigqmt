# 开发期本机主执行与稳定后迁移决策

日期：2026-09-14  
状态：`USER_DECISION_RECORDED / NO_RUNTIME_ROLE_CHANGE / NO_ORDER_CHANGE`

## 已确认顺序

1. 开发机/PVE1 Win11 `192.0.2.105` 在开发期间同时作为 QMT 主力运行机；本机现有目录保持：
   - `C:\BigQMT\work\kitling_bigqmt`
   - `C:\BigQMT\work\国金QMT交易端模拟`
   - `C:\BigQMT\work\国金证券QMT交易端`
2. 模拟账户在多主机功能开发期间，唯一执行机候选为 `192.0.2.105`。只有现有模拟盘门禁和本机
   执行开关满足时才能下单；记录主机角色本身不授予下单权限。
3. `192.0.2.121` 作为独立 Coordinator/Agent Gateway 候选，不运行 QMT，不直接下单。
4. `192.0.2.125` 与 `198.51.100.113` 暂不接管执行：
   - `192.0.2.125` 是开发稳定后的首选迁移目标；
   - `198.51.100.113` 是后续备用/只读节点。
5. 正式账户继续 `READ_ONLY`。开发机是模拟盘主力不等于正式账户获得执行权。

## 开发期拓扑

```text
OpenClaw / 手机
       |
       v
192.0.2.121 Coordinator + Agent Gateway
       |
       v
192.0.2.105 开发机 + 唯一模拟 ACTIVE_EXECUTOR 候选
       |
       +-- F盘 BigQMT / Redis / Tray / Dashboard / State
       +-- F盘 模拟QMT与正式QMT（正式只读）

192.0.2.125  FUTURE_MIGRATION_TARGET / READONLY_PREP
198.51.100.113   FUTURE_STANDBY / READONLY_PREP
```

## 迁移触发条件

从 `192.0.2.105` 迁移到 `192.0.2.125` 前至少满足：

- M01–M06 对应功能和证据通过；
- Coordinator、Host Agent、OpenClaw 查询和模拟订单意图闭环通过；
- 本机不存在状态未知的活动委托，成交、持仓和策略袖套已对账；
- Windows 一键迁移包在干净目录通过安装、升级和回滚；
- `192.0.2.125` 先完成只读 QMT/Bridge/Host Agent 验证；
- Coordinator 进入迁移冻结，两台主机均确认只读；
- 本机 SQLite、配置哈希、审计与凭据迁移清单准备完成；
- 用户单独确认执行权迁移。

## 迁移步骤

1. 暂停模拟策略新增订单；
2. 等待或人工处理活动委托，完成账户/持仓/成交/袖套对账；
3. Coordinator 撤销 `192.0.2.105` 租约并增加 fencing token；
4. 备份本机运行库和审计，复制经过校验的 release 到 `192.0.2.125` 本地 E 盘；
5. 125 以 `STANDBY_READONLY` 启动并再次对账；
6. 用户确认后，Coordinator 只向 125 发放新的模拟 `ACTIVE_EXECUTOR` 租约；
7. 105 降为开发/只读节点，旧 token 在 Coordinator、Host Agent 和 Bridge 三层均被拒绝；
8. `198.51.100.113` 保持 `STANDBY_READONLY`，以后另做接管演练。

本记录覆盖此前“125 立即作为长期主执行机”的顺序建议，但不否定 125 作为最终迁移目标的硬件评估。
本轮没有修改 QMT、Tray、Bridge、Redis、Coordinator 或订单权限。
