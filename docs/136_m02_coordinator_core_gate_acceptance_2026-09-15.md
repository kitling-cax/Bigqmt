# M02 Coordinator 核心门禁验收

日期：2026-09-15
范围：本机纯本地；只验证 Coordinator 控制面核心，不连接 QMT、Redis、OpenClaw，不产生订单。

本文是 docs/127_m01_m02_local_coordinator_acceptance_2026-09-14.md 的补充。127 号文档已交付
控制面核心与五份 v1 合同，但 M02 gate「两个 fake host 永远不能对同一账户同时持有有效
executor lease」的验收证据尚未正式收口。本文记录该 gate 的最终证据并将 M02 关闭。

## gate 定义

> two fake hosts can never hold a valid executor lease for the same account

即：无论两个主机以何种顺序、通过各自独立的连接竞争同一账户的租约，最终只有
fencing token 最新的一方持有有效租约，旧租约在任何后续写操作（preview / confirm）
及显式校验中都必须被拒绝。

## 证据测试

- tests/test_coordinator_core.py::test_single_active_lease_and_fencing：单店内先后授予
  host-105 / host-125，旧租约 preview 抛 StaleLeaseError。
- tests/test_coordinator_core.py::test_two_fake_hosts_cannot_hold_valid_lease_simultaneously
  （本轮新增）两个独立 CoordinatorStore 句柄共享同一 SQLite 文件，分别以 host-105 /
  host-125 授予同一账户租约：current_lease 仅指向 host-125，token 递增 (n -> n+1)，
  旧租约 validate_lease 与 preview_intent 均拒绝。
- test_heartbeat_and_takeover_leave_only_latest_host_current：心跳接管后仅最新主机为
  current，旧 token 校验失败。
- test_epoch_invalidates_old_lease：epoch 递增后旧租约失效。
- test_expired_lease_and_duplicate_confirm_are_rejected：过期租约与重复 confirm 均拒绝。

## 验收结果（2026-09-15）

py -3.12 -m pytest -q tests/test_coordinator_core.py => 6 passed

租约写入使用 SQLite BEGIN IMMEDIATE 串行化读-改-写，避免双主获得相同 fencing token；
account_leases 以 account_id 为主键，同一账户在库内逻辑上只保留一条租约行；
validate_lease 对 host_id / mode / fencing_token / epoch / expires_at 逐项校验。

## 关闭判定

M02 gate 达成：同一账户在任意时刻最多一个有效 executor lease；旧租约无论以 preview /
confirm 还是显式 validate 均 fail-closed。M02 状态由 IN_PROGRESS 收口为 PASSED
（weight 15），整体专项验证进度由 15% 提升至 30%。

## 安全边界

- 模拟账户 90000001 本轮 orders_enabled=false，未开启、未下单。
- 正式账户 90000002 保持只读，未触碰其任何交易路径。
- 本轮纯本地测试，未连接 Redis / QMT / OpenClaw，未部署 .121。

