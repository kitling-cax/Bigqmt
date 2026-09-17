# OpenClaw 双主机 Agent 注册决策

日期：2026-09-14  
状态：`USER_MAPPING_CONFIRMED / NO_MCP_SCOPE / NO_ORDER_AUTHORIZATION`

## 用户确认的 Agent 映射

| OpenClaw 主机 | 主 Agent | 下单候选 Agent | 角色 |
|---|---|---|---|
| `198.51.100.113` | `chief` | `execution` | `chief` 为编排/只读；`execution` 为该主机的模拟交易候选 |
| `192.0.2.125` | `kitling` | `xiaocai`（小财） | `kitling` 为编排/只读；`xiaocai` 为该主机的模拟交易候选 |

图片与用户本轮明确说明共同构成该映射的记录来源。该映射覆盖此前共享盘两份 inventory 对候选 Agent
产生的歧义：`execution` 和 `xiaocai` 都是有效的、但归属于不同 OpenClaw 主机的候选执行 Agent。

## 权限与唯一执行规则

1. `chief`、`kitling` 和所有研究、风控、组合、筛选、内容、运维等 Agent 都是 `observer` 或
   `reporter`，不能调用 preview/confirm/cancel 订单工具。
2. `execution@198.51.100.113` 与 `xiaocai@192.0.2.125` 都登记为
   `candidate_executor_simulation`，但当前没有 BigQMT MCP scope、token 或订单能力。
3. 同一账户同一时刻只能有一个可确认订单的 Agent identity。Coordinator 将按
   `(account_id, active_executor_host, active_executor_agent_id)` 三元组验证；不能因为两台 OpenClaw
   都有候选 Agent 而出现双入口下单。
4. 开发期间模拟 `ACTIVE_EXECUTOR` 候选是 `192.0.2.105`。在 AP5 之前，两台远程 OpenClaw 的候选
   Agent 都只能等待，不创建 token；后续需由用户明确指定开发期采用哪一个作为唯一手机订单入口。
5. 当执行权未来迁移到 125 时，建议把 `xiaocai@192.0.2.125` 作为本地主机的唯一订单 Agent；若
   未来切换到 113，则建议把 `execution@198.51.100.113` 作为本地主机的唯一订单 Agent。切换前必须
   撤销另一 Agent 的 simulation executor scope 并完成账户对账。
6. 正式账户 `90000002` 不映射任何下单 Agent，继续 `READ_ONLY`。

## AP5 前仍需的明确输入

在发放任何模拟订单 token 前，用户仍需给出：

- 开发期 `192.0.2.105` 主力运行时，唯一允许接收手机订单的 Agent：`execution@198.51.100.113` 或
  `xiaocai@192.0.2.125`；
- 该 Agent 可接受指令的飞书手机/频道身份；
- 是否仅允许 v1.1.15、允许的证券/策略范围，以及单笔/单日模拟风险上限；
- AP5 的明确批准。

本记录只登记角色，不安装 MCP/Skill，不更改 OpenClaw 配置，不创建凭据，不修改 Coordinator/Host Agent，
不调用 QMT/Redis/Bridge，不发送订单。
