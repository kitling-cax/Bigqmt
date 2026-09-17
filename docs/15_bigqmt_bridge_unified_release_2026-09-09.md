# BIGQMT_BRIDGE 统一桥接发布契约

状态：`CANDIDATE / DEFAULT_LOCKED`。本文件定义一份桥接代码在模拟盘与正式盘的复用方式；
不表示模拟或正式环境已获订单权限。

## 一份桥接代码，两个物理隔离配置

`BIGQMT_BRIDGE.py` 是唯一的 QMT 策略入口。它复用已在模拟 QMT 验证过的本地加载器、
Redis RPC、行情、账户、持仓、委托、成交回调、QMT 下单与撤单适配代码。这样后续环境切换
不需要编辑桥接代码、替换策略逻辑或复制一套新模块。

但模拟和正式**绝不共用**配置文件、QMT Python 部署目录、Redis 命名空间或账号标识：

| 环境 | 代码 | 部署配置 | 初始权限 |
| --- | --- | --- | --- |
| 模拟账户 `90000001` | 同一发布包 | 模拟 QMT 本机私有配置 | 只读、锁单 |
| 正式账户 `8890****6688` | 同一发布包 | 正式 QMT 本机私有配置 | 完整代码、运行时只读锁单 |

部署包至少包含 `BIGQMT_BRIDGE.py`、`BIGQMT_REDIS_DRYRUN.py`（验证过的本地加载器）、
`bigqmt_signal_trader/`、`bigqmt_signal_trader_strategy.py`、
`bigqmt_signal_trader_redis_rpc_runtime.py` 以及本机私有
`bigqmt_signal_trader_local_config.py`。私有配置不进入项目发布清单，不含 QMT 登录密码。

## 订单能力的固定实现与放行方式

桥接中已经预置 QMT 下单和撤单适配；未来不为“允许模拟下单”或“允许正式下单”修改桥接代码。
所有写入路径都经过同一个 `OrderAdmissionPolicy`，且 RPC 与 QMT 内部信号消费各检查一次。

模拟环境需同时满足：

1. RPC 订单方法显式启用；
2. `environment=SIMULATION`；
3. `orders_enabled` 与 `execution_consumer_enabled` 均为真；
4. 行情/账户运行前预检和 v1.1.15 parity 均为 `ALLOWED`；
5. 存在模拟盘确认记录；
6. 订单的策略名在独立袖套白名单中，且账号与模拟配置一致。

正式环境使用相同代码，但还必须同时满足模拟验收已验证、正式执行批准、正式确认记录和
正式环境隔离。当前正式包为 `CAPABLE_CODE / READ_ONLY_LOCKED`：代码已具备未来执行能力，
但订单开关、执行消费者、预检和 parity 均锁定，用户尚未作出正式盘下单授权。
`portable/config/qmt_execution_admission.example.py` 是两种私有配置的锁定模板。

## 当前部署顺序

当前 QMT 中的 `BIGQMT_REDIS_DRYRUN` 仍是唯一已运行的策略。`BIGQMT_BRIDGE` 尚未部署进
QMT，也不应与它并行连接同一 Redis 请求通道；否则可能出现两个消费者争用同一请求或相互
重置运行时。

下一次模拟盘部署按下列不可跳过顺序执行：

1. 保存现有 `BIGQMT_REDIS_DRYRUN` 的只读健康证据；
2. 停止该策略，确认 Redis RPC 无旧心跳；
3. 将本候选发布包同步到**模拟** QMT 的 Python 目录，并核对加载版本；
4. 在 QMT 新建名称为 `BIGQMT_BRIDGE` 的 Python 策略，粘贴入口内容，以分钟线启动；
5. 仅验证 ping、账户、持仓、委托、成交、Redis 和行情；订单 RPC 继续关闭；
6. 只有桥接只读证据通过后，才可停止/归档旧 `DRYRUN` 作为回退版本。

该部署是 P02--P05 回归，不是 P06 下单测试。若 Bridge 启动失败，立即停止它并恢复
`BIGQMT_REDIS_DRYRUN`；不改变账户持仓，也不尝试订单/撤单。
