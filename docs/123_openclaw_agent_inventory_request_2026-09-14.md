# OpenClaw 多 Agent 信息采集请求：BigQMT 接入前置

日期：2026-09-14  
状态：`READ_ONLY_INVENTORY_REQUEST / NO_DEPLOYMENT_AUTHORIZATION`

## 目的

为后续 BigQMT MCP/Skill 接入建立 Agent 权限清单。OpenClaw 已部署于：

- `192.0.2.125`
- `198.51.100.113`

本次只采集信息，不安装 Skill、不注册 MCP、不修改配置、不重启 Gateway/Agent、不读取或输出密码、token、
API key、cookie、私钥或完整配置文件。

## 请返回的 Agent 信息

每台 OpenClaw 主机分别返回以下 JSON 结构。字段缺失时写 `UNKNOWN`，不得猜测。

```json
{
  "reported_at": "ISO-8601 timestamp",
  "host_ip": "192.0.2.125 or 198.51.100.113",
  "gateway_status": "RUNNING | STOPPED | UNKNOWN",
  "openclaw_version": "version or UNKNOWN",
  "agents": [
    {
      "agent_id": "exact stable agent identifier",
      "display_name": "human readable name",
      "enabled": true,
      "workspace": "path or UNKNOWN",
      "current_purpose": "short description",
      "channel_providers": ["telegram/discord/... or NONE"],
      "channel_account_aliases": ["alias only, no token"],
      "can_receive_phone_message": true,
      "authorized_operator_identity_format": "provider user/chat identifier format only; do not disclose private token",
      "proposed_bigqmt_role": "observer | reporter | candidate_executor_simulation | none",
      "notes": "constraints, duplicate channel ownership, or UNKNOWN"
    }
  ],
  "channel_conflicts": [
    "same bot/channel token used by more than one active agent, if known"
  ],
  "security_observations": [
    "only non-secret findings, e.g. externally reachable control UI"
  ]
}
```

## 分配原则

- 所有 Agent 初始都是 `observer` 或 `none`；
- `reporter` 只允许写入其自身 NAS 报告目录；
- 未来只选择一个确切 `agent_id` 作为 `candidate_executor_simulation`；
- 在用户明确批准 AP5 前，不为任何 Agent 创建 `executor_simulation` token；
- 不创建 `qmt-executor-production`；正式账户保持只读；
- 同一个聊天机器人/token 若被多个活跃 Agent 使用，必须先解决路由冲突，不能同时承担交易入口。

## 返回后将执行的动作

用户根据 inventory 指定：

1. 负责模拟订单的 `agent_id`；
2. 该 Agent 的主机（125 或 113）；
3. 允许发送交易指令的手机/频道身份；
4. 是否允许该 Agent 生成 NAS 报告。

在此之前，BigQMT 项目只会准备候选 MCP/Skill 发布包，不会给 OpenClaw、Coordinator、Windows Host Agent
或 QMT 发出下单指令。
