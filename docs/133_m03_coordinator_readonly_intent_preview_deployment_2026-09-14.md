# M03 Coordinator 空只读 Intent Preview 部署验收

日期：2026-09-14  
环境：`192.0.2.121` Coordinator 与 `192.0.2.105` 开发主机。

## 已部署

Coordinator 的 `serve.py` 已在 `.121` 备份后替换并重启服务。备份目录：

```text
/opt/bigqmt-coordinator/backups/20260914_223607_before_readonly_intent_preview
```

`systemctl` 返回 `active`。首次脚本结果中的 curl 失败是脚本错误使用 `127.0.0.1:18443`，
而服务实际绑定 `.121` 局域网地址；部署本身没有失败。脚本现已改为使用参数化的
`http://192.0.2.121:18443/healthz`。

## 真实连通验收

从 `.105` 读取：

```text
GET http://192.0.2.121:18443/healthz                         -> 200
GET /api/v1/host-agent/intents?account_id=90000001&host_id=192.0.2.105 -> 200
```

Host Agent 客户端 probe 返回：`intent_count=0`、`readonly=true`、
`orders_enabled=false`。

此端点未读取或暴露 SQLite intent、未进行 lease 操作、未调用 QMT/Redis/Bridge，且没有
订单提交、确认或执行路径。
