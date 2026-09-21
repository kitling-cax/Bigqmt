# BIGQMT_BRIDGE 双账户主机部署说明

适用主机：`.125`、`.113` 及其他已部署 BigQMT 托盘的 Windows 主机。

本说明只包含部署方法，不包含 QMT 密码、Fact Secret、授权 Key 或 Redis 密码。

## 一、发布包位置

每台主机的项目目录下均应有：

```text
releases\bridge\kitling-bigqmt-bridge-20260909-rc3\
├─ BIGQMT_BRIDGE_SIMULATION.zip
└─ BIGQMT_BRIDGE_PRODUCTION_CAPABLE_LOCKED.zip
```

模拟账户：由本机私有 `machine.local.json` 注入，本机 Redis `127.0.0.1:6379`。

正式账户：由本机私有 `machine.local.json` 注入，本机 Redis `127.0.0.1:6380`。

两个 Redis 都是本机服务，不要把 Redis 端口改成另一台电脑的地址。

## 二、解压与备份

1. 先退出目标 QMT 中旧的 `BIGQMT_REDIS_DRYRUN` 或旧版 `BIGQMT_BRIDGE`。
2. 分别解压两个 ZIP 到临时目录。
3. 备份目标 QMT 的 `python` 目录中已有的同名文件，建议加日期后缀保存。
4. 模拟包和正式包必须分开操作，不能交叉复制配置文件。

## 三、复制模拟账户文件

从 `BIGQMT_BRIDGE_SIMULATION` 解压目录复制 `qmt_python` 内全部内容到模拟 QMT 的 Python 目录。

必须包含：

```text
BIGQMT_REDIS_DRYRUN.py
bigqmt_signal_trader_strategy.py
bigqmt_signal_trader_redis_rpc_runtime.py
bigqmt_signal_trader_local_config.py
bigqmt_signal_trader\           （整个目录）
```

不要只复制 `BIGQMT_BRIDGE.py`，它是 QMT 编辑器入口，不能单独运行。

## 四、复制正式账户文件

从 `BIGQMT_BRIDGE_PRODUCTION_CAPABLE_LOCKED` 解压目录复制 `qmt_python` 内全部内容到正式 QMT 的 Python 目录。

正式包必须使用正式包自己的 `bigqmt_signal_trader_local_config.py`，不能使用模拟包配置。

## 五、在 QMT 中建立策略

模拟 QMT 和正式 QMT 各执行一次：

1. 打开 QMT 策略编辑器。
2. 新建 Python 策略，名称必须为 `BIGQMT_BRIDGE`。
3. 打开对应包中的：

```text
qmt_editor\BIGQMT_BRIDGE.py
```

4. 将文件全部内容粘贴到 QMT 策略编辑器。
5. 保存策略。
6. 选择分钟线运行。

`BIGQMT_BRIDGE.py` 两个账户内容相同，不需要改名或改代码。

## 六、启动顺序

建议顺序：

1. 启动对应账户的 QMT 并完成登录。
2. 启动对应账户的 BigQMT 托盘。
3. 托盘自动检查并拉起本机 Redis、Dashboard 和 MiniQMT。
4. 在 QMT 中启动 `BIGQMT_BRIDGE`。
5. 等待 30 秒心跳周期。

同一个 QMT 终端内不要同时运行 `BIGQMT_REDIS_DRYRUN` 和 `BIGQMT_BRIDGE`。

## 七、启动验证

托盘状态应达到：

```text
QMT        UP
MiniQMT    UP（若启用）
Redis      UP
Bridge     UP
Dashboard  UP
Tray       UP
```

本机端口：

```text
模拟 Redis       6379
正式 Redis       6380
模拟 Dashboard   17890
正式 Dashboard   17891
```

Coordinator 页面应能看到对应主机和账户心跳：

```text
http://192.168.1.121:18443/
```

如果 Bridge 仍为 DOWN，先检查 QMT 中策略是否真正启动，以及策略日志是否出现 `kitling-bigqmt-bridge` 和 Redis RPC 初始化信息。

## 八、当前安全边界

- 模拟包和正式包均保留统一 Bridge 代码。
- 当前发布包的订单/撤单执行开关默认锁定。
- 正式账户当前只做账户、持仓、委托、成交和行情通信验证。
- 不要通过修改 `BIGQMT_BRIDGE.py` 或简单修改布尔值开启下单。
- 后续如批准模拟下单，将通过独立的本机授权、运行控制和 Coordinator 执行租约流程处理。

## 九、迁移到其他 Windows 主机

迁移时只需：

1. 复制对应主机的 BigQMT 项目目录。
2. 复制两个 Bridge ZIP 包。
3. 按本说明复制到该主机实际的 QMT Python 目录。
4. 检查 `machine.local.json` 中的本机 QMT 根目录、数据目录和 Coordinator 地址。
5. 不复制另一台电脑的 Redis 数据库、运行锁或托盘状态文件。

策略源文件保持一致；账户配置、本机路径和授权文件必须使用目标主机自己的本地配置。
