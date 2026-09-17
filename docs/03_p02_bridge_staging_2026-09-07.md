# P02 大 QMT Bridge staging 记录

日期：2026-09-07

## 只读环境检查

- 模拟版 QMT 根目录：`C:\BigQMT\work\国金QMT交易端模拟`
- `bin.x64\Lib\site-packages\qmt_api`：存在
- `bin.x64\Lib\site-packages\redis`：存在
- `bin.x64\Lib\site-packages\pandas`：存在
- 独立 `bin.x64\python.exe`：未发现；应通过 QMT 模型交易环境加载 Python 策略入口。
- `python36.dll` 和 `bin.x64\Lib`：存在，符合 QMT 内置 Python 3.6 运行形态。

## Bridge staging

参考 `xtquant_big_convert` 的 Redis Bridge 已复制到：

`C:\BigQMT\work\kitling_bigqmt\staging\qmt_bridge_simulation`

包括 QMT 编辑器入口、Redis RPC runtime、桥接核心包和无凭据配置模板。

## 验证结果

- 使用主机 Python 3.12 进行语法编译检查：通过。
- 已复制桥接入口和核心包到模拟 QMT `python` 目录：`C:\BigQMT\work\国金QMT交易端模拟\python`
- 尚未在 QMT 模型交易界面加载。
- 尚未连接账户、持仓、委托、成交。
- `rpc_allow_order_methods` 仍保持关闭，不允许远程下单。

## 下一步

在模拟 QMT 中加载 staging 的 `BIGQMT_REDIS_DRYRUN.py` 前，需要确定模拟账户标识和 QMT 模型交易加载方式；加载后先只验证 Bridge 启动日志、Redis RPC ping 和行情查询。
