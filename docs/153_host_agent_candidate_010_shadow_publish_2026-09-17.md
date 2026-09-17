# Host Agent 0.1.0 Shadow 候选包发布

日期：2026-09-17

已生成并发布不含任何 Secret、密码、token 或执行 Key 的 Host Agent facts-only 候选包：

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\releases\host_agent\candidate\0.1.0-shadow\
```

包内包含：

- `scripts/host_agent/collect_runtime_fact.py`
- `scripts/host_agent/deliver_fact_outbox.py`
- `scripts/coordinator/manage_fact_identity.py`
- facts-only 所需的最小 `src/kitling_bigqmt` 模块集
- `config/machine.local.example.json`
- `README_INSTALL.md`
- `checksums.sha256`

安装说明要求 `.125` 与 `.113` 在各自本机生成独立 Fact Secret；不共享 `.105` Secret，不把 Secret 写入 NAS。默认 Coordinator 端点为 `.121:18666` Shadow，投递器拒绝非 Shadow 端口，除非显式覆盖。

该候选包只上报策略运行、成交/NAV/checkpoint 等事实，不提供订单、Lease、确认、QMT RPC 或 Redis RPC 能力。`.125/.113` 尚未安装或接管执行；发布仅完成候选包与校验清单准备。
