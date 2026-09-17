# BigQMT OpenClaw 独立只读包安装任务（替代旧版说明）

适用对象：

- `.125` / `192.0.2.125`：主 Agent `kitling`，WSL/Linux
- `.113` / `198.51.100.113`：主 Agent `chief`，Windows

旧版 `0.1.0-readonly` 依赖 BigQMT 项目目录和 Python 3.12，**不要继续安装它**。请使用 NAS channel 当前指向的 `openclaw-bigqmt-bundle-0.1.1-readonly`。

## 重要简化

新版是独立 observer MCP：

- 仅要求现有 Python **3.11 或更高版本**；不安装 Python 3.12，不运行 winget，不申请 UAC；
- 不要求本机有 BigQMT/QMT/Redis，也不搜索或创建空的 `D:\bigqmt`；
- 不读取或复制 `.105` 的运行数据、数据库、凭据、QMT 配置；
- 不创建 token、不申请执行租约、不下单。

## 发布源

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\channels\openclaw.json
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\releases\openclaw\candidate\openclaw-bigqmt-bundle-0.1.1-readonly\
```

预期 manifest SHA-256：

```text
4B96C971AA1E601DE27CE9E5072A8DF2581832BD0D7EAA2A68A2CBDC1EB84395
```

## 安装步骤

1. 从 NAS 复制完整 release 到**本机**专用目录，例如：
   - Windows `.113`：`C:\Users\developer\.openclaw\bigqmt-readonly\0.1.1-readonly\`
   - WSL `.125`：`~/.openclaw/bigqmt-readonly/0.1.1-readonly/`
2. 校验 `manifest.json` SHA-256 与 `checksums.sha256` 的 6 个 payload 文件。任一失败即删除 staging、停止。
3. 复制：

```text
mcp/bigqmt_readonly.local.example.json
```

为同目录下：

```text
mcp/bigqmt_readonly.local.json
```

保持唯一 endpoint：

```json
{"coordinator_endpoint":"http://192.0.2.121:18443"}
```

这不是凭据，不能加入 token 或其他字段。

4. 将 `skill/SKILL.md` 安装到当前 OpenClaw 本机 Skill 目录。
5. 注册 MCP：
   - `.113` 使用 `mcp/server.example.windows.json`，保持 `py -3.11`；
   - `.125` 使用 `mcp/server.example.linux.json`，使用已存在的 `python3` / Python 3.11+；
   - 将模板中的 `<LOCAL_OPENCLAW_BIGQMT_DIR>` 替换为本机 `mcp` 目录的绝对路径。

如果 OpenClaw 的配置路径或 CLI 语法未知，先读取本机现有配置并报告，不要覆盖全局配置、不要安装未知依赖。

## 验收

执行 OpenClaw 的 Skill check 与 MCP probe/status，并用 stdio 测试 `tools/list`。只允许显示：

```text
bigqmt_get_fleet_status
bigqmt_get_executor_preview
bigqmt_get_project_progress
```

调用这三个工具各一次。预期 `.105` 仍是当前模拟候选；`.125` / `.113` 未接入 Host Agent，不能成为执行机。

如果出现订单确认、preview order、lease 写入、QMT RPC、Redis、SQL、Shell 或 token 工具，立即禁用该 MCP 注册并报告异常。

## 报告

分别写入：

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\reports\openclaw\125\20260914_install_report.md
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\reports\openclaw\113\20260914_install_report.md
```

写明：Python 版本、本机目录、manifest/6 文件校验、Skill/MCP probe、工具列表、三个查询摘要和阻塞项。不得写密码、token、QMT 配置或敏感账户数据。
