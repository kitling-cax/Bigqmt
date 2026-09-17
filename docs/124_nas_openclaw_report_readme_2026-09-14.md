# BigQMT Coordinator / OpenClaw 规划报告

本目录是供 OpenClaw 与人工审阅的只读规划材料，不是可执行部署包。

阅读顺序：

1. `01_bigqmt_v2_implementation_plan.md`：当前唯一实施顺序和批准点；
2. `02_mcp_skill_coordinator_plan.md`：MCP、Skill、NAS 本地安装和 Coordinator 迁移设计；
3. `03_openclaw_agent_inventory_request.md`：请 OpenClaw 返回的多 Agent 信息模板。

当前状态：

- 开发机 `192.0.2.105` 是当前模拟主力执行机候选；
- Coordinator 尚未部署；预定初期访问地址为 `https://192.0.2.121:18443/`；
- OpenClaw 只能先提供 Agent inventory 和后续只读查询；
- 未指定 agent_id、未批准 AP5 前，禁止为任何 Agent 创建模拟订单权限；
- 正式账户继续只读。

请只返回 `03_openclaw_agent_inventory_request.md` 所要求的非敏感 Agent 清单。不得在本目录中保存或输出密码、
token、API key、cookie、私钥、完整配置或券商凭据。
