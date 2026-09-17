# M01 machine.local.json 单点覆盖验收补充

日期：2026-09-15
范围：本机纯本地；只校验配置与路径投影，不连接 QMT、Redis、OpenClaw，不产生订单。

本文件是 docs/127_m01_m02_local_coordinator_acceptance_2026-09-14.md 的补充。127 号文档覆盖了 Coordinator 控制面与五份 v1 合同，但未把「machine.local.json 单点覆盖」这条 M01 交付链的验收记录补齐。本文补齐该链路，作为 M01 gate 的证据。

## 权威实现

- src/kitling_bigqmt/machine_config.py
  - validate_machine_local(root)：对 config/machine.local.json 做 JSON Schema 校验，fail-closed。
  - effective_config(root, profile)：单一投影，输出 data_directory / coordinator / qmt_root / bin_x64 / redis / state_db / audit_dir / dashboard_port / ready_port / orders_enabled。
  - effective_config_hash(root, profile)：对确定性投影做 SHA-256。
  - audit_hardcoded_paths(root)：只读盘点 config/scripts/src 下的本地绝对路径、UNC 路径与端口字面量。
  - 权威加载器：load_gateway / load_tray_profiles / load_qmt_paths / apply_data_lake_root 与 coordinator_endpoint.resolve_coordinator 统一从 machine.local.json 取本机覆盖。

## 验收结果（2026-09-15）

py -3.12 -m pytest -q tests/test_machine_config.py tests/test_machine_config_audit.py => 14 passed

覆盖：非法 JSON、非对象、非法 schema_version 均 fail-closed；合法 partial override 通过；simulation / production_readonly 投影正确；orders_enabled 始终 False；有效配置哈希确定且随覆盖变化；硬编码绝对路径 / UNC 路径 / 端口字面量审计命中。

关联回归（Coordinator 控制面基线）：py -3.12 -m pytest -q tests/test_coordinator_endpoint.py tests/test_coordinator_core.py tests/test_coordinator_lease_projection.py tests/test_host_agent_client.py tests/test_host_agent_intent_preview.py => 17 passed

## verify 脚本输出摘要

py -3.12 scripts/verify_machine_local_config.py --evidence-dir runtime_data/evidence/simulation

- machine_local_valid: true
- machine_local_validation: []
- effective_config_hash.simulation: 63e6ce27400982002a10c3fb97efe6af61d2cbc556194fcc209adc45aefc339e
- effective_config_hash.production_readonly: 8188b0f4415c9fe00306c985756b36acf704789839a6037b4d1a3b1f4117f478
- simulation：environment=simulation、orders_enabled=false、redis 127.0.0.1:6379 db5、dashboard_port=17890、ready_port=58600、qmt_root=C:/BigQMT/work/国金QMT交易端模拟
- production_readonly：environment=production_readonly、orders_enabled=false、redis 127.0.0.1:6380 db5、dashboard_port=17891、ready_port=58600、qmt_root=C:/BigQMT/work/国金证券QMT交易端
- hardcoded audit：scanned=config,scripts,src、finding_count=94
- readonly=true

证据文件：runtime_data/evidence/simulation/machine_local_gate_20260915T145419+0800.json

verify_machine_local_config.py 在 machine_local_valid=false 时返回退出码 1，构成可固化的启动前门禁。

## gate 达成说明

1. invalid local config fails closed：schema 缺失、override 非法 JSON、非对象、schema_version 非法均由 validate_machine_local 明确返回错误，测试已覆盖，verify 脚本按错误返回非零退出码。
2. all entry points resolve the same effective paths and endpoints：effective_config 作为 single-source projection，已被核心运行时代码接入（dashboard_status、tray_health、local_backup、bridge_probe、miniqmt_launcher_cli、qmt_launcher_cli、run_lake_cycle、export_readonly_snapshot_to_lake 等）。

## 运行时 loader fail-closed（方案 B，硬失败）

machine.local.json 的运行加载语义在本轮按「方案 B」收口：

- 缺失文件：config/machine.local.json 不存在时仍回退为 {}，保持可迁移默认行为。
- 文件存在但非法：非法 JSON 或 JSON 顶层非对象时，load_machine_local 抛出
  MachineLocalConfigError，且异常从所有运行时加载器向上传播——load_gateway、
  load_tray_profiles、effective_config 均拒绝启动，不再静默回退默认值。
- scripts/verify_machine_local_config.py 捕获该异常、不打印 traceback；此刻
  machine_local_valid=false、hash/summary 置为 None，并以退出码 1 作为启动前门禁。

专项测试：tests/test_machine_config_fail_closed.py（7 项），覆盖缺失回退、非法 JSON、
非对象，以及 load_gateway / load_tray_profiles / effective_config 的异常传播。
合并运行 machine_config / machine_config_audit / machine_config_fail_closed 共 21 passed。

## entry-point rollout 收口（2026-09-15）

- 研究、诊断、比对、缓存检查及 v1.1.15 模拟运行脚本的缺省配置均改由
  `machine_config.load_gateway(root, "simulation")` 提供；显式 `--config` 仍保留，便于复现历史配置。
- `portable_deployment.check_portable_deployment` 改用 `load_tray_profiles` 与 `load_gateway`，
  因而校验的是 machine.local.json 覆盖后的有效 QMT 根目录、Redis 端口和状态库路径。
- `py -3.12 -m compileall -q src scripts` 通过；M01/托盘针对性测试 26 passed；完整项目回归
  175 passed。此前列出的直接 JSON 读取项已全部收口（备份清单中的原件路径保留用于审计归档）。

本轮复核（2026-09-15 18:03 Asia/Shanghai）：`scripts/verify_machine_local_config.py` 再次返回
`machine_local_valid=true`，并生成 `runtime_data/evidence/simulation/machine_local_gate_20260915T180330+0800.json`；
两套有效配置哈希与前次一致，说明入口统一没有改变既定本机覆盖结果。

## 安全边界

- 模拟账户 90000001 本轮 orders_enabled=false，未开启、未下单。
- 正式账户 90000002 保持只读，未触碰其任何交易路径。
- 本机未连接 Redis / QMT / OpenClaw；未部署 .121。
