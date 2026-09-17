# BigQMT OpenClaw 只读候选包安装任务

对象：

- `192.0.2.125` 的 OpenClaw 主 Agent：`kitling`（WSL/Linux 环境）
- `198.51.100.113` 的 OpenClaw 主 Agent：`chief`（Windows 环境）

目标：在两台机器上分别安装同一个 `openclaw-bigqmt-bundle-0.1.0-readonly` 候选版本，并完成只读 MCP 与 Skill 探测。

本任务只安装 observer-only 查询能力。禁止创建或索取 QMT 密码、Redis 密码、Coordinator 执行 token；禁止申请/续期/切换执行租约；禁止调用 QMT、Redis、SQL、Shell 下单或任何订单确认接口。正式账户 `90000002` 永远只读。

## 发布源与版本规则

NAS 发布源：

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\
  channels\openclaw.json
  releases\openclaw\candidate\openclaw-bigqmt-bundle-0.1.0-readonly\
```

两台主机使用相同的代码 release；不要为 `.125` 和 `.113` 建立不同代码分支。必须分开的只有：

- 每台机器本地的 BigQMT 运行目录；
- 每台机器的 `config/machine.local.json`；
- 每个 OpenClaw Agent 的配置、SecretRef 和未来 token；
- 每台机器自己的安装报告与日志。

禁止从 SMB 路径直接运行 Skill 或 MCP。必须先复制到本地版本目录，校验成功后才启用；NAS 临时不可用不应影响已经启用的本地只读查询。

## 安装前检查

1. 读取 `channels/openclaw.json`，确认：
   - `release=openclaw-bigqmt-bundle-0.1.0-readonly`
   - `scope=observer_readonly`
   - `orders_enabled=false`
2. 将该 release 完整复制到本机 staging 目录。不要覆盖已启用的旧版本。
3. 根据 release 内 `checksums.sha256` 校验全部 6 个 payload 文件；任一不匹配则删除 staging 并停止。
4. 校验 `manifest.json` 的 SHA-256：

```text
06902B25BB375E6FF85AA06586F00F6C0643F305406FA57F63C95B83C13FED13
```

## 本地 BigQMT 覆盖配置

本候选包的 `project_overlay` 要复制到**本机** BigQMT 项目根目录中，不能直接在 NAS overlay 中运行。

保留本机现有路径与端口，仅在本机 `config/machine.local.json` 的 `coordinator` 节写入正确 Host ID：

`.125`：

```json
"coordinator": {
  "endpoint": "http://192.0.2.121:18443",
  "host_id": "192.0.2.125"
}
```

`.113`：

```json
"coordinator": {
  "endpoint": "http://192.0.2.121:18443",
  "host_id": "198.51.100.113"
}
```

这只是只读 Coordinator 定位信息，不是执行许可。不得复制 `192.0.2.105` 的运行数据库、Redis AOF、Credential Manager 凭据、QMT 配置或订单状态库。

## OpenClaw 注册

1. 将 `skill/SKILL.md` 安装到本机 OpenClaw 的 Skill 目录。
2. 使用 `mcp/server.example.json` 作为本机 MCP 注册模板。将 `working_directory` 改为本机 BigQMT 项目目录。
3. `.113` Windows 通常使用：

```text
py -3.12 scripts/openclaw_bigqmt_readonly_mcp.py
```

4. `.125` WSL/Linux 使用已安装的 Python 3.12 命令，例如：

```text
python3.12 scripts/openclaw_bigqmt_readonly_mcp.py
```

5. 仅注册以下三个工具：

```text
bigqmt_get_fleet_status
bigqmt_get_executor_preview
bigqmt_get_project_progress
```

如果本机 OpenClaw 的实际配置文件路径或 CLI 命令与预期不同，先报告实际情况；不要猜测、不要覆盖全局 OpenClaw 配置、不要为此安装未知第三方 MCP 包。

## 必须通过的探测

完成本地注册后执行 OpenClaw 自身的 MCP probe/status 与 Skill check。还要通过 stdio 发送：

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

验收要求：只返回三个只读工具；不得出现 `confirm`、`preview_order`、`cancel`、`lease` 写入、QMT RPC、Redis、SQL、Shell 或其他订单工具。

随后调用 `bigqmt_get_executor_preview`，预期只能看到当前 `.105` 为模拟候选；`.125` 和 `.113` 在未接入各自 Host Agent 前不应显示为可执行候选。

## 安装报告

请分别把报告写入 NAS（只写各自报告目录）：

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\reports\openclaw\125\20260914_install_report.md
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\reports\openclaw\113\20260914_install_report.md
```

报告须包含：本机 OS/Agent 名称、本地安装路径、release/manifest hash、6/6 checksum 结果、Skill check、MCP probe、实际可见工具列表、`bigqmt_get_executor_preview` 摘要，以及任何阻塞项。不得在报告中写 token、密码、完整私密配置或账户敏感数据。

成功安装不等于获得执行权。后续要先由用户指定唯一的 simulation executor Agent，并完成认证、人工确认、短租约与本机二次校验；在此之前始终 `orders_enabled=false`。
