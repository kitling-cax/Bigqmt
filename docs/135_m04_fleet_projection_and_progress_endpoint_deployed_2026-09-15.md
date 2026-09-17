# 135 — M04 舰队监控/进度投影 + Coordinator 只读端点上线（2026-09-15）

## 范围
把本机最新 `scripts/coordinator/serve.py` 部署到 `192.0.2.121`（systemd `kitling-bigqmt-coordinator`），使在线只读 Coordinator 从“旧版发散快照”升级为：返回真实 program phase 的 `/api/v1/progress`、新增只读聚合 `/api/v1/fleet`，并补上 `/api/v1/host-agent/intent-preview-status`（旧版 404）。

## 变更
1. 修复 `serve.py._scan_program_yaml`：原实现 `strip()` 后匹配 `status:`，导致缩进的里程碑 `status:`（PASSED/IN_PROGRESS/NOT_STARTED）逐行覆盖顶层 program phase，最终会错报为 `NOT_STARTED`。改为仅匹配列首（column-0）键，并补采顶层 `updated_at`。
2. `response_payload` 完成：
   - `/api/v1/progress` → `load_progress()` 快照（`phase` / `overall_verified_percent` / `updated_at` + `readonly:true` / `orders_enabled:false`）。
   - `/api/v1/fleet` → `hosts` + `executor_preview` + `intent_preview` + `progress`，`control=READ_ONLY_FLEET_PROJECTION`。

## 测试
- 新增 3 项（progress 快照、progress 端点、fleet 投影）到 `tests/test_coordinator_bootstrap.py`，该文件 9 passed。
- Coordinator 相关子集（bootstrap / endpoint / core / lease_projection / intent_preview）25 passed。

## 部署方式（免交互）
- 本机为 Windows OpenSSH 9.5，仅密码登录（无 plink/sshpass/密钥）。用临时 `SSH_ASKPASS` 助手 + `SSH_ASKPASS_REQUIRE=force` 免除交互；远端 sudo 用 `echo <pw> | sudo -S -v` 缓存后执行。
- 流程：scp 上传 serve.py 与 progress/multi_host_program.yaml → 远端备份 → install → `systemctl restart` → `/healthz` 校验。临时 askpass 文件用后即时删除。

## 在线实测（192.0.2.121:18443）
- `/api/v1/progress` → `phase=M01_M04_READONLY_FLEET_IMPLEMENTATION_IN_PROGRESS`、`overall_verified_percent=15`、`updated_at=2026-09-15T16:10:00+08:00`、`readonly=true`、`orders_enabled=false`。
- `/api/v1/fleet` → 200，`mode=readonly-fleet`、`control=READ_ONLY_FLEET_PROJECTION`，含 host `.105`（6 项服务 UP，双账户）、executor_preview（sim eligible、prod 不可执行）、intent_preview、progress。
- `/api/v1/host-agent/intent-preview-status` → 200（旧版 404），`orders_enabled=false`，两账户 `EMPTY_READONLY`。
- `systemctl is-active` → `active`；`/healthz` → `readonly-foundation`。

## 安全边界（未变）
- 全链路 readonly / `orders_enabled=false`；prod `90000002` 仍 `READ_ONLY`；无租约写入、无下单、无 token。

## 备份
- `/opt/bigqmt-coordinator/backups/20260915_184137_before_fleet_projection/`
- `/opt/bigqmt-coordinator/backups/20260915_184500_before_updated_at_fix/`

## 状态
- M02（Coordinator core）仍 IN_PROGRESS：gate「两个 fake host 不能同时对同一账户持有有效执行租约」的验收证据未在本轮闭环。
- M04（舰队监控/进度）仍 IN_PROGRESS：本轮完成的是只读 JSON 投影与进度端点，Fleet Dashboard UI、Tray 客户端、告警尚未完成。
- `overall_verified_percent` 维持 15%，不虚增。

