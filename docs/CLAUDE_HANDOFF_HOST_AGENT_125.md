# Claude 接手文档：`.125` Host Agent 0.1.0 Shadow 安装

目标工作目录：

```text
E:\kitling_QMT_work\kitling_bigqmt
```

目标主机：`192.0.2.125`

本任务只安装 **facts-only Host Agent**，不启用订单、Lease、确认或任何 QMT/Redis 写入能力。

## Claude 必须先做的事

1. 阅读本文件和 `instructions\host_agent\125_vscode_host_agent_install_steps_20260917.md`。
2. 确认当前终端是 Windows PowerShell，不是 WSL。
3. 确认 `py -3.12 --version` 可用；不可用时停止并报告，不要自行安装未知版本。
4. 校验 `host_agent_candidate\0.1.0-shadow\checksums.sha256`。
5. 找到 `.125` 本机真实的 `native_tray.jsonl`；找不到时停止，不得创建伪造日志。

## 安装范围

候选包位置：

```text
E:\kitling_QMT_work\kitling_bigqmt\host_agent_candidate\0.1.0-shadow
```

将候选包复制到实际运行目录：

```text
C:\ProgramData\Kitling\BigQMT\HostAgent\0.1.0-shadow
```

Fact Secret 必须在本机生成到：

```text
C:\ProgramData\Kitling\BigQMT\secrets\host-125-fact-shadow-20260917.json
```

不得将 Secret 写入工作目录、NAS、Git 或报告。

## Coordinator 端点

只允许：

```text
http://192.0.2.121:18666/api/v1/facts/ingest
```

禁止访问或修改：

```text
http://192.0.2.121:18443
```

## 必须执行的验证

1. 本地采集一条 `STRATEGY_RUNTIME` 事实。
2. 投递到 `18666` Shadow。
3. 检查响应：

```text
status=ACCEPTED 或 EMPTY
facts_only=true
orders_enabled=false
pending=0
```

4. 故意断开 Shadow 时确认返回 `RETRY_PENDING`，且 pending 不被删除。
5. 不启动任何订单相关命令。

## 报告

写入：

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\reports\openclaw\125\20260917_host_agent_install_report.md
```

报告必须包含：

- host_id
- 包版本
- checksums 结果
- Python 版本
- 本地采集结果
- Shadow HTTP 响应摘要
- pending 数量
- 错误和阻塞原因

报告禁止包含 Secret、密码、token、执行 Key 或完整凭据文件。

## Claude 完成回报格式

```text
HOST_AGENT_125_RESULT=PASSED 或 BLOCKED
host_id=192.0.2.125
package=0.1.0-shadow
endpoint=http://192.0.2.121:18666/api/v1/facts/ingest
facts_only=true
orders_enabled=false
pending=<数量>
report=<报告路径>
```

不要注册新的下单 MCP，不要修改 OpenClaw 全局配置，不要修改 `.121:18443`。
