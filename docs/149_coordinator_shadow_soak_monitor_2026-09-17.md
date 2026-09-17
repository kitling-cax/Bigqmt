# `.121:18666` Shadow soak 定时巡检

日期：2026-09-17 06:10（Asia/Shanghai）

## 实施

新增只读探针 `scripts/coordinator/soak_probe.py`，每次只执行 GET：

- 权威 `18443/readyz`；
- Shadow `18666/readyz`，必须为 `mode=shadow_readonly`；
- Shadow `/api/v1/progress`，必须 `readonly=true` 且 `orders_enabled=false`。

`.121` 已安装：

- `/opt/bigqmt-coordinator-shadow/soak_probe.py`；
- `kitling-bigqmt-coordinator-shadow-soak.timer`，每 5 分钟触发；
- 日志：`/var/log/kitling-bigqmt-coordinator-shadow/soak.jsonl`。

systemd 服务采用 root 仅写专用日志目录，`NoNewPrivileges`、`ProtectSystem=strict`、`ProtectHome` 和 `PrivateTmp` 开启；不访问 Docker socket、数据库、QMT、Redis 或 NAS。

## 首次验证

```text
timer: active
sample: ok=true
authority_readyz: 200
shadow_readyz: 200, mode=shadow_readonly
shadow_progress: 200, readonly=true, orders_enabled=false
```

此前首次运行失败是因为尝试写入容器专用状态父目录，已改为隔离 `/var/log` 子目录并验证通过。当前 Shadow 容器和权威服务均正常。

