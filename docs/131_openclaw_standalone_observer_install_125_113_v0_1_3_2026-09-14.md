# BigQMT OpenClaw v0.1.3 统一发布说明

`0.1.2-readonly` 已在 `.125` 与 `.113` 完成 6/6 payload 和 stdio 只读验收，且没有
注册全局 MCP、没有 token/租约/下单行为。该版本的 payload 是正确的，但验收暴露两个跨平台
发布风险：Windows 文本模式会使 manifest/checksum 产生 CRLF；PowerShell 5.1 的
`Set-Content -Encoding UTF8` 会产生 JSON BOM。

因此 `0.1.3-readonly` 是最终的统一注册候选：README、`manifest.json`、
`checksums.sha256` 与 `channel.openclaw.json` 全部以 UTF-8 **无 BOM**、固定 **LF** 原始字节
生成。它不增加、删除或改变任何 MCP 功能；仍严格只包含三个 observer-only 工具。

## 发布源

```text
\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\releases\openclaw\candidate\openclaw-bigqmt-bundle-0.1.3-readonly\
```

固定 manifest SHA-256：

```text
0D5602C4C2C5BAC5ADAB2F031373458545188C62B320144F78AB69242F1360F8
```

发布源验证结果：6/6 payload 完整、manifest/checksums/README/channel 均 LF-only 且无 BOM。

## 本机配置编码规则

`bigqmt_readonly.local.json` 必须是 UTF-8 无 BOM。Windows PowerShell 5.1 不得用：

```powershell
Set-Content -Encoding UTF8
```

可使用：

```powershell
[System.IO.File]::WriteAllText(
  'C:\path\to\bigqmt_readonly.local.json',
  '{"coordinator_endpoint":"http://192.0.2.121:18443"}',
  [System.Text.UTF8Encoding]::new($false)
)
```

文件只允许该 endpoint 字段；不得写 token、密码、账户或订单权限。

## 执行步骤

1. `.125` 与 `.113` 均从 NAS 本地复制 0.1.3 至新版本目录，不覆盖各自已审计的 0.1.2；
2. 对 manifest、6 个 payload 与 README 291 bytes / SHA-256
   `1c8ea177bfe2dfdad9fa8b24911bd6076ce49313efdb6ff808105bad1eeadddc` 做 raw-binary 校验；
3. 用上述 UTF-8 无 BOM 规则创建本机 local JSON；
4. 执行 stdio `tools/list` 和三个读取工具。仅允许：
   `bigqmt_get_fleet_status`、`bigqmt_get_executor_preview`、
   `bigqmt_get_project_progress`；
5. 报告写入各自 `reports/openclaw/<host>/20260914_install_report_v0.1.3.md`；
6. **只有两侧报告都通过且用户明确授权后**，才注册到各自 OpenClaw 全局配置。

0.1.2 的双侧验收报告应永久保留，作为功能/安全审计证据；0.1.3 仅消除元数据与配置编码歧义。
