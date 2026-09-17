# xtquant_big_convert 源码研究记录

日期：2026-09-08  
对象：本地检出 `C:\BigQMT\work\xtquant_big_convert`，提交
`90a9736e8d880b26a9d204b4ea80079461c17bb7`（Release 0.3.26）。

本记录只基于本地源码、文档和离线测试；没有调用 QMT 下单接口。

## 一句话定位

`xtquant_big_convert` 是“大 QMT 进程内服务端 + 外部 Python 客户端”的兼容桥接库。
它把大 QMT 的 `ContextInfo`、运行时注入的 `passorder` / `get_trade_detail_data`
等能力，经 Redis、ZMQ 或 MySQL 传输层暴露给外部程序，并提供部分 MiniQMT 风格
`xtquant` API 兼容层。

它不是策略池、虚拟子账户、数据湖或 Dashboard 产品；这些应由 `kitling_bigqmt`
自身负责。

## 核心调用链

```text
QMT 模型交易策略生命周期
    -> BIGQMT_REDIS_DRYRUN.py（QMT 沙箱本地加载器）
    -> bigqmt_signal_trader_redis_rpc_runtime.py（本地配置、账号、传输选择）
    -> bigqmt_signal_trader_strategy.py（init / adjust / 回调）
    -> SignalTradingApp + BigQmt* adapters
    -> Redis / ZMQ / MySQL RPC transport
    -> 外部 xtquant 兼容客户端、研究系统、数据湖适配层
```

### 关键源码职责

| 模块 | 作用 | 对本项目的价值 |
|---|---|---|
| `src/BIGQMT_REDIS_DRYRUN.py` | QMT 沙箱中的本地模块加载器，处理 `__file__` 缺失、导入白名单和运行时全局函数捕获 | 可参考，但不要自行修改后直接粘贴到编辑器 |
| `src/bigqmt_signal_trader_strategy.py` | 处理 `init`、`handlebar/adjust`、委托/成交回调、RPC 服务启动和诊断 | 大 QMT Bridge 核心参考 |
| `src/bigqmt_signal_trader/adapters/market_bigqmt.py` | 以 `ContextInfo`/原生 `xtdata` 封装行情与历史数据 | QMT 行情适配层候选 |
| `src/bigqmt_signal_trader/adapters/position_bigqmt.py` | 通过 `get_trade_detail_data` 读取资金、持仓、委托、成交 | QMT 交易状态适配层候选 |
| `src/bigqmt_signal_trader/adapters/order_bigqmt.py` | 把兼容订单请求映射到 QMT `passorder` | 仅后续受控执行层参考 |
| `src/bigqmt_signal_trader/redis_rpc.py` | RPC 方法、订单写权限、异步回报、序列化与应答 | 可保留为外部控制面的候选 |
| `src/bigqmt_signal_trader/transports/` | Redis / ZMQ / MySQL 的可替换传输实现 | 本项目第一阶段只用 Redis |
| `src/bigqmt_signal_trader/qmt_launcher.py` | 启动、关闭、重启和可选的交互式登录自动化 | 最后阶段再评估，不进入当前启动链路 |

## 已验证的安全边界

1. `adapter_factory.py` 的默认 `dryrun` 使用空信号源与
   `DryRunOrderGateway`，不会调用 QMT `passorder`。
2. `bigqmt_signal_trader_redis_rpc_runtime.py` 的
   `RPC_ALLOW_ORDER_METHODS` 默认值为 `False`；即使 RPC 服务已启动，订单和撤单
   方法也必须显式开启才可调用。
3. 真正接入 Redis 信号源、切换 `mode="bigqmt"`、并显式放开订单方法后，
   才有可能经 `passorder` 发送委托。
4. 当前项目 Redis 使用本机 `127.0.0.1:6379`、db 5；模拟阶段继续保持
   `rpc_allow_order_methods=False`。

## 源码能力与本项目边界

| 目标能力 | 参考项目是否已提供 | 本项目应如何使用 |
|---|---|---|
| 大 QMT 最新行情与历史行情 | 大部分提供 | 作为 QMT 数据接入器；由本项目转换并写入数据湖 |
| 资金、持仓、委托、成交 | 提供 `get_trade_detail_data` 适配 | 只读验证通过后接入交易状态库和 Redis 实时快照 |
| 实时委托/成交回报 | 提供回调事件推送 | 接入本项目审计事件流，不直接作为策略收益账本 |
| 远程订单 | 提供，但需显式开关 | 模拟阶段禁用；正式盘另设审批和风控门 |
| MiniQMT API 兼容 | 提供部分 shim | 仅为 `kitling_AI量化_review` 的迁移适配，不能替代策略层 |
| 多策略虚拟子账户 | 未提供 | 本项目独立实现策略资金账本、归因、复利、仓位限额 |
| 数据湖/Parquet/DuckDB | 未提供 | 本项目独立写入 F 盘数据层；Redis 仅实时缓存/消息 |
| Dashboard | 未提供核心产品 | 本项目独立实现 |

## 当前 QMT 接入问题的源码解释

仓库测试 `test_entry_not_a_strategy.py` 明确指出：若入口在“编辑器运行”或
“独立 Python 进程”模式执行，QMT 不会触发生命周期 `init(ContextInfo)`，也不会
注入交易全局函数；表面看像启动了，实际上 RPC 服务不会运行。

当前模拟 QMT 日志符合以下未验证状态：

- 策略名已进入 QMT 的 `configFormula` 索引；
- 模型/公式层已订阅 `000300` 分钟线；
- 但没有 `[bigqmt_signal_trader] init ok`、`[bigqmt_rpc] started` 或 Redis
  Bridge 业务键；
- 反复出现 `load file [BIGQMT_DRYRUN_WRAPPER] parse error`。

因此不能再把“QMT 显示运行”视为 Bridge 已运行。下一步应先验证这个券商 QMT
版本中，哪一种“模型交易实例”能够真实调用 `init(ContextInfo)`，再选择入口形式；
不应继续通过叠加包装代码猜测。

## 推荐采用与不采用

采用：

- QMT 行情/交易状态适配思想；
- `init` / `adjust` / 委托成交回调的生命周期结构；
- Redis RPC 的只读优先、订单开关、幂等状态与日志诊断；
- QMT 重启和登录能力作为后置可选模块。

不直接采用：

- 将全部策略、账户分配、收益归因塞入 Bridge；
- 将 Redis 当作历史数据仓库；
- 未加本项目级风控就开启参考项目的订单 RPC；
- 在验证失败时把完整入口代码反复粘贴到 QMT 编辑器。

## 测试基线

已运行四组核心离线测试：应用编排、dry-run 下单、Big QMT adapters、Redis RPC。
结果为 `89 passed in 2.90s`。该测试不连接当前 QMT、不发送 Redis 信号、不产生订单。

## 下一阶段建议

1. 保持当前模拟账户和订单 RPC 禁用。
2. 在 QMT UI 内定位并验证“模型交易实例”的正确加载方式，目标仅为获得
   `init ok` 与 `adjust ok`。
3. 仅在生命周期确认后，启用 Redis 只读 RPC，验证资金/持仓/委托/成交和一条行情查询。
4. 把验证通过的 QMT 数据接入本项目 Redis 实时层，再异步落 F 盘 Parquet/DuckDB。
5. 之后独立实现多策略虚拟资金账本、仓位归因和收益曲线；不把这部分依赖在
   `xtquant_big_convert` 内。
