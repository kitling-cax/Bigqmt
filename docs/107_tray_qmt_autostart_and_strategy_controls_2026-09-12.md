# P16 候选：QMT 托盘启动、策略运行开关与正式恢复框架

## 已部署内容

- 模拟与正式只读托盘各自检测对应 QMT 安装目录下的进程；QMT 缺失时只启动本 profile 的 `XtItClient.exe`。
- 托盘和两个 CMD 启动器均强制使用 PowerShell `-STA`，并通过独立的 Windows `DETACHED_PROCESS` 启动器脱离调用终端。这样关闭命令窗口、开发宿主或启动脚本不会连带关闭通知区托盘；非 STA 主机将明确失败，而不是留下“进程存在但没有托盘图标”的假运行状态。
- 终端状态、FormulaServer 58600 监听、Bridge 快照、Redis、Dashboard 与订单锁显示在托盘菜单。
- 托盘额外每分钟进行一次仅允许 `ping` 的 Bridge 在线探针。它不读取账户、行情、委托或成交，更没有订单能力；用来防止旧 SQLite 快照掩盖“QMT 已启动但 Bridge 未恢复”。
- 托盘不会自动杀死或重启仍在运行的 QMT。操作员可从菜单显式重启所属 profile 的 QMT；这不会影响另一套 QMT。
- 模拟盘增加 `Enable v1.1.15 simulated strategy execution` 持久化开关。关闭时，策略采样与记账继续，但自动和手动订单周期均被拦截。
- 正式盘增加 `Allow recovery of approved formal strategies` 意图开关。它不解锁订单，也不会准入策略；`formal_strategy_admissions.json` 目前为空。
- Dashboard 的正式盘投影可读取自身 SQLite WAL 内未来被正式准入的策略袖套，但绝不读取模拟盘袖套、信号或收益。

## 登录安全

- 默认模式为 `exe`，优先让 QMT 自己恢复会话；禁止使用会因发现 MiniQMT 而切换目标的 `auto` 模式。
- 必要时可使用 `mode=login`。凭据仅存储在 Windows Credential Manager，目标名为 `KitlingBigQMT/QmtLogin/<profile>`。
- 首次保存凭据必须由本机用户在可信终端执行：

  `py scripts/manage_qmt_login_credential.py set --profile simulation`

- 新电脑首次部署应先执行：

  `py -3.12 -m pip install -r requirements-tray.txt`

  随后使用 `py scripts/check_portable_deployment.py --profile simulation`（正式盘使用
  `production_readonly`）核对 QMT 根目录、启动器、Bridge 在线探针和硬订单锁。该检查不启动服务、
  不访问账户，也不创建订单。

- 凭据不会写入项目、Redis、日志、命令行或 Dashboard。锁屏、RDP 注销、验证码或二次确认出现时，登录自动化必须失败关闭。

## 当前验证

- 2026-09-12：模拟盘和正式盘 QMT 进程均已按各自安装路径被识别；58600 端口监听中。
- 两个托盘启动后，Redis 6379/6380、Dashboard 17890/17891、Bridge 快照和订单锁健康检查均通过。
- 模拟策略总开关默认关闭；正式恢复意图默认关闭；正式订单仍硬锁。
- 正式 Bridge 的一次真实 RPC 验证发现其运行配置为 `6380/db0`、主机为 `6380/db5`。原配置已备份至 `deploy/backups/20260912_production_qmt_redis_db0_before_fix/`，部署配置已对齐为 db5；等待 QMT 内的 Bridge 策略重启加载。

## 尚待终端证据

- 不能在不关闭当前已登录终端的情况下证明“冷启动后的券商会话恢复”或“凭据输入登录”。
- 真正的 QMT 就绪还需在一次受控重启中收集 Bridge RPC ping、账户、持仓与行情的 read-only 证据；58600 监听本身不构成登录成功证明。
- 因此 P16 状态为 `CANDIDATE_DEPLOYED_PENDING_CONTROLLED_RESTART_EVIDENCE`，不是 `VERIFIED`。

## 2026-09-12 受控重启的实际结果

- 模拟终端的安装目录级进程拉起已成功，但终端随后对券商网关
  `180.169.107.19:56001` 多次连接超时；该终端尚未恢复为可查询会话。
- `BIGQMT_BRIDGE` 在重启后没有产生新的 RPC 输出。因此托盘的 QMT 行现在明确
  标注为 `PROCESS ONLY`：进程存在和 58600 监听均不等同于账号登录或 Bridge 就绪。
- 订单锁与模拟策略总开关均保持关闭。本轮没有创建任何订单、撤单或订单意图。
- 要完成 P16 终端证据，需先在 QMT 中正常登录并启动 `BIGQMT_BRIDGE`，再收集
  ping、账户、持仓、委托、成交和行情的只读快照；正式盘还需要重新加载已经对齐的
  `6380/db5` Bridge 配置。
