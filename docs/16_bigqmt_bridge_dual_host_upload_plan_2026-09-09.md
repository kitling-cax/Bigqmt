# BIGQMT_BRIDGE 双环境上传运行计划

状态：`RC3_BUILT / SIMULATION_READ_ONLY_UPLOAD_NEXT`

## 交付目标

生成一份固定的 `BIGQMT_BRIDGE` 桥接代码和两个隔离配置包：

- 模拟包：连接模拟 QMT、模拟 Redis `127.0.0.1:6379`，账号 `90000001`；
- 正式完整能力锁定包：连接正式 Redis `127.0.0.1:6380/DB 5`，订单接口当前硬锁；
- 两包使用相同桥接源码和发布编号，只有本机配置与运行数据目录不同；
- 本轮上传只验证只读链路，不进入任何订单或撤单测试。

## 上传前必须由项目完成

1. QMT Python 3.6 语法、导入和单元测试通过；
2. submit、batch、原生 passorder、cancel 和内部信号路径均有失败关闭测试；
3. 桥接核对实际 QMT Python 目录，误复制环境配置时拒绝写操作；
4. 撤单前从券商委托事实核对 `order_sys_id` 和策略归属；
5. 生成模拟/正式两个带 SHA256 清单的 ZIP，禁止混用；
6. 正式 Redis `6380` 配置完成但在正式只读验证前不暴露局域网；
7. 回滚包保留当前 `BIGQMT_REDIS_DRYRUN`。

## 用户上传顺序

不得同时第一次上传。先模拟、后正式：

1. 停止模拟 QMT 的 `BIGQMT_REDIS_DRYRUN`；
2. 备份模拟 QMT 当前 Bridge 文件；
3. 解压模拟发布包到模拟 QMT `python` 目录；
4. 在 QMT 新建 `BIGQMT_BRIDGE`，粘贴发布包内的编辑器入口，分钟线运行；
5. 只读检查 release id、Redis ping、账号、持仓、委托、成交和行情；
6. 模拟端通过只读回归后，再以相同步骤部署正式完整能力锁定包；
7. 正式端页面必须显示 `PRODUCTION READ ONLY`，且 ping 返回订单方法关闭。

任何一步出现环境、账号、Redis、目录、版本或行情不一致，立即停止新策略并恢复旧
`BIGQMT_REDIS_DRYRUN`。Dashboard 或 Codex 不参与运行时放行。
