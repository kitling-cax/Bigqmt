# P15 托盘只读健康检查（2026-09-09）

状态：`IN_PROGRESS`。健康检查已实现并通过测试，但正式只读 profile 当前隔离 Redis 6380 不可用，因此结果保持 `FAIL_CLOSED`，没有任何自动恢复或重启动作。

## 检查内容

`src/kitling_bigqmt/tray_health.py` 和 `scripts/check_tray_health.py` 对每个 profile 检查，单项最多进行两次有界尝试：

- 项目目录和 profile 配置是否存在且 JSON 可读；
- 对应 Redis 的只读 `PING`；
- 独立 runtime control 是否保持 `orders_enabled=false` 与 `execution_consumer_enabled=false`；
- 模拟 profile 的 loopback Dashboard `/healthz` 是否返回 `read_only=true`；
- 正式 profile 不复用模拟 Dashboard，暂时报告 `DEFERRED`。

运行方式：

```powershell
py scripts\check_tray_health.py --profile simulation
py scripts\check_tray_health.py --profile production_readonly
```

## 本次结果

- `simulation`：`HEALTHY`，Redis 6379 返回 `PONG`，Dashboard 200，只读锁有效；
- `production_readonly`：`FAIL_CLOSED`，Redis 6380 当前超时；订单开关仍强制为 false，未尝试重启正式 QMT/Redis；
- 自动测试：`39 passed`；
- 没有调用 QMT RPC、订单/撤单接口或 Redis 写命令。
- 托盘运行日志确认：模拟 profile 进入 `HEALTHY`；正式 profile 在 Redis 6380 不可用时保持 `FAIL_CLOSED`。
- 重试只针对只读 PING/HTTP healthz，不执行进程重启、不写 Redis、不改变订单开关。

## 下一步

P15.2 增加结构化健康日志、有限次数的安全重试和 Tray 菜单状态刷新；只有健康检查恢复后才允许标记 profile 可观测，仍不会自动开启任何订单权限。
