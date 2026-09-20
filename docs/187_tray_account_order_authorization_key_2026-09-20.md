# 托盘账户下单授权 Key（2026-09-20）

## 1. 目标

每台 Windows 策略主机、每个 QMT 账户独立保存一个本机下单授权 Key：

- 模拟账户 Key 与正式账户 Key 分开；
- 没有有效 Key 时，账户只能进行查询、快照、心跳和状态展示，不能进入下单门禁；
- Key 有效只是下单的必要条件，不是充分条件；
- Key 不替代策略开关、短时运行窗口、Coordinator 单执行机检查、风控、幂等和券商前置校验；
- 正式账户仍受当前 `production_readonly` 策略保护。安装正式账户 Key 只完成本机资格准备，不会单独开放正式下单。

## 2. 本机存储

Key 明文只保存在 Windows Credential Manager：

```text
KitlingBigQMT/OrderAuthorization/simulation
KitlingBigQMT/OrderAuthorization/production_readonly
```

凭据同时记录当前账户号作为绑定对象。托盘和 Python 门禁只显示：

- 是否安装；
- 是否与当前账户匹配；
- SHA-256 指纹；
- `VALID / MISSING / ACCOUNT_MISMATCH / INVALID` 状态。

禁止把 Key 写入 Git、NAS、`machine.local.json`、日志、诊断报告或聊天记录。

## 3. 托盘操作

右键账户托盘，打开 **下单授权 Key 管理**：

1. **查看本账户 Key 状态**：显示是否有效及当前保护状态；
2. **加入本账户授权 Key**：遮罩输入两次，最少 32 个字符，写入 Windows Credential Manager；
3. **删除本账户授权 Key**：先输入托盘删除密码，再二次确认；删除后账户立即退回只读状态。

托盘主状态区持续显示 `下单授权 Key` 状态，每 30 秒刷新一次。状态变化写审计事件，但审计内容不含 Key。

建议使用密码管理器生成不少于 32 个字符的随机 Key，并在目标 Windows 机器上直接粘贴到托盘遮罩框。不要通过 Git、普通 NAS 文件或聊天传输。

## 4. 下单门禁顺序

本地订单入口统一调用 `execution_admission.require_admission_for_root()`，按失败即关闭原则检查：

1. 账户和 profile 匹配；
2. 本账户本机授权 Key 存在、有效且账户绑定一致；
3. 策略短时运行窗口已明确开启且未过期；
4. Coordinator 可达，并确认本机是该账户唯一可执行候选；
5. 其他既有风控、幂等和 Bridge/QMT 前置条件继续成立。

任一条件失败都不写入订单 RPC。Key 删除后，下一次订单门禁立即返回 `LOCAL_ORDER_KEY_MISSING`。

## 5. `.125` / `.113` 更新步骤

两台运行主机分别在自己的主机分支合入 `feature/tray-authorization-key`，然后：

```powershell
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_native_account_trays.ps1
```

确认测试通过、两个 EXE 的 SHA-256 与 `tray/BigQMT_native_tray_checksums.sha256` 一致后：

1. 退出两个旧托盘；
2. 用新构建产物覆盖本机托盘 EXE；
3. 分别启动模拟和正式托盘；
4. 检查两者初始状态均为 `下单授权 Key：未安装｜账户只读`；
5. 只在计划负责执行的账户托盘中本地加入对应 Key；
6. 查看 Key 状态，确认账户绑定和指纹；
7. 不执行真实订单，用门禁测试确认无 Key 返回 `LOCAL_ORDER_KEY_MISSING`。

## 6. 验收标准

- 无 Key：只读功能正常，订单入口拒绝；
- 模拟 Key 不会授权正式账户，正式 Key 也不会授权模拟账户；
- Key 绑定错误：托盘显示账户不匹配，订单入口拒绝；
- 删除 Key：无需重启托盘，立即恢复只读；
- 日志、Git diff、诊断报告和进程命令行中均不存在 Key 明文；
- 同一账户在两台主机都安装 Key 时，Coordinator 冲突检查仍必须拒绝执行，并发出多执行候选告警；
- 正式 `production_readonly` 在现阶段即使安装 Key，仍不能下单。

## 7. 回滚

如需紧急停止某账户的本机下单资格，优先在托盘中选择 **删除本账户授权 Key**，输入托盘删除密码并确认。该操作不删除 QMT 登录凭据、不停止查询服务、不影响账户快照和 Host Agent 心跳。
