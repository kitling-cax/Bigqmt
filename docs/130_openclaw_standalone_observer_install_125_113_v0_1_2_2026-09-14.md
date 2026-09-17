# BigQMT OpenClaw 独立只读包 v0.1.2 安装与复核

适用对象：

- `192.0.2.125` / 主 Agent `kitling`（WSL/Linux）；
- `198.51.100.113` / 主 Agent `chief`（Windows）。

## 发布结论

`0.1.1-readonly` 的功能探测通过，但其 `README_INSTALL.md` 在 Windows/Linux
复制链路中发生 CRLF/LF 字节漂移，无法满足 **6/6 完整性校验**。因此该版本不得注册为
活动 MCP。请只使用 `0.1.2-readonly`。

`0.1.2-readonly` 固定以 UTF-8/LF 原始字节发布，已在发布源完成 6/6 文件哈希及
manifest/channel 双重哈希验证。

## 发布源与固定哈希

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\channels\openclaw.json
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\releases\openclaw\candidate\openclaw-bigqmt-bundle-0.1.2-readonly\
```

manifest SHA-256：

```text
D2A2230997B909A9B3C7BA919DFF69EF27219FBB7887781A14CD3ED9A18BAB67
```

README 固定校验值：291 bytes，SHA-256
`1c8ea177bfe2dfdad9fa8b24911bd6076ce49313efdb6ff808105bad1eeadddc`。

## 约束

- 只需已有 Python 3.11+；不得运行 `winget`、安装 Python、触发 UAC；
- 不需要 BigQMT 项目目录、QMT、MiniQMT、Redis、数据库或凭据；
- release 必须先复制到本机目录运行，禁止直接从 NAS 执行；
- 不创建 token、不申请或续期租约、不下单、不改 Coordinator；
- 不覆盖全局 OpenClaw 配置。若本机配置语法未知，只报告并等待人工确认。

## 安装

1. 从 NAS 复制完整 release 至本机新目录：
   - `.125`：`~/.openclaw/bigqmt-readonly/0.1.2-readonly/`
   - `.113`：`C:\Users\developer\.openclaw\bigqmt-readonly\0.1.2-readonly\`
2. 核对 manifest SHA-256，随后根据 `checksums.sha256` 核对全部 **6** 个 payload。
   任一不匹配即停止；尤其不得忽略 README。
3. 把 `mcp/bigqmt_readonly.local.example.json` 复制为同目录
   `bigqmt_readonly.local.json`，内容仅保留：

   ```json
   {"coordinator_endpoint":"http://192.0.2.121:18443"}
   ```

4. 安装 `skill/SKILL.md` 至该机 OpenClaw 本地 Skill 目录。
5. MCP 注册仅可在人工确认目标机既有 OpenClaw gateway 配置后进行：
   `.125` 采用 `mcp/server.example.linux.json`，`.113` 采用
   `mcp/server.example.windows.json`。将模板占位目录改为上一步的**本机**绝对路径。

## 只读验收

完成本地 stdio probe 后，`tools/list` 必须且只能返回：

```text
bigqmt_get_fleet_status
bigqmt_get_executor_preview
bigqmt_get_project_progress
```

各调用一次，返回必须同时具备 `readonly=true` 与 `orders_enabled=false`。当前预期只有
`.105` 是模拟账户候选，`.125/.113` 不是 Host Agent、没有执行租约；正式账户
`90000002` 一律不可执行。

若任何工具涉及订单、租约写入、QMT、Redis、SQL、Shell、密码或 token，立即禁用本次
注册并报告。

## 报告位置

`.125` 将 v0.1.2 复核结果写入：

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\reports\openclaw\125\20260914_install_report_v0.1.2.md
```

`.113` 写入同名 `reports\openclaw\113\` 目录。保留 `.125` 的 0.1.1 报告作为
完整性门禁拒绝的审计证据。
