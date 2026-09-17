# P02 Bridge 运行测试记录

日期：2026-09-08

测试范围：模拟版 QMT；只读诊断；未调用下单接口，未修改正式版 QMT。

## 结论

本次测试为“部分通过，Bridge 验证失败”，不能判定为可运行成功。

## 已通过

- QMT 已将策略注册为 `BIGQMT_REDIS_DRYRUN`，并写入自身的策略索引。
- QMT 模型交易已尝试启动该策略，日志记录了策略 ID、模拟账户和入口路径。
- QMT 已对 `SH000300` 发起日线 K 线和均线数据请求，并收到历史数据回调。
- 模拟 Redis 服务仍可用，端口为 `127.0.0.1:6379`。

## 未通过

- `XtClient_20260908.log` 在策略启动时多次出现：
  `load file [BIGQMT_REDIS_DRYRUN] parse error`
- 随后出现该策略的 `try stop` / `stop error`，说明策略没有建立稳定运行实例。
- QMT 日志没有出现预期的 `[bigqmt_signal_trader] init ok`、`[bigqmt_rpc] started` 等 Bridge 启动标记。
- Redis 当前没有发现 `bigqmt*` 业务键，也没有持续的 Bridge 客户端连接；因此不能证明 QMT 已向 Redis 发布行情或账户数据。
- 未验证账户、持仓、委托、成交 RPC；未进行任何下单操作。

## 重要判断

QMT 的“策略已显示/已点击运行”和“Python Bridge 已运行”是两层状态。本次前一层通过，后一层失败。

QMT 编辑器保存的部分策略文件会变成内部编码的一行文件，因此不能仅以主机 Python `py_compile` 判断 QMT 策略是否有效。但本次同时存在 QMT 自身的 `parse error`，且完全没有 Bridge/Redis 启动痕迹，仍应按 Bridge 未启动处理。

## 下一步安全动作

1. 先停止模拟盘中的 `BIGQMT_REDIS_DRYRUN`，不改正式盘。
2. 保留当前日志和策略索引作为失败样本。
3. 优先改用“小型 QMT 包装策略”调用 `bigqmt_signal_trader_strategy`，不要继续把完整 Bridge 入口直接粘贴到 QMT 编辑器中；入口和依赖模块仍放在模拟版 `python` 目录。
4. 重新运行后，必须同时看到 Bridge `init ok`/RPC 启动日志和 Redis 业务键，才进入账户、持仓、行情 RPC 验证。
5. 在上述证据出现前，不允许接入正式盘，也不允许发送订单。

## 已准备的下一轮入口

已在项目 staging 准备 `BIGQMT_DRYRUN_WRAPPER.py`。它只导出 QMT 回调并使用
`configure(mode="dryrun")`，不会打开订单方法。复制到 QMT 编辑器时必须保持 ASCII，
并保留第一行 `#coding:gbk`。

后续观察发现，此版本 QMT 对“只导入后再导出回调名”的包装策略仍产生
`load file ... parse error`，且没有任何 Bridge 输出。已额外准备
`BIGQMT_DRYRUN_DIRECT_CALLBACKS.py`：它在编辑器入口中直接定义 `init`、
`handlebar` 等回调，再转发给 Bridge，作为下一轮模拟盘验证入口。

## 原生生命周期探针结论

随后以不导入 Bridge、Redis 或任何第三方模块的 `QMT_LIFECYCLE_PROBE.py`
做了最小测试。其内容只包含 `init(ContextInfo)` 和 `handlebar(ContextInfo)`
两项原生回调及 `print`。

QMT 仍然记录 `load file [QMT_LIFECYCLE_PROBE] parse error`，并出现
`try stop`；公式输出中没有 `[qmt_probe] init ok` 或
`[qmt_probe] handlebar ok`。因此当前故障已排除为 Bridge、Redis、导入包和
分钟线设置问题，根因落在该 QMT 的“新建 Python 策略”文件加载/解析链路。

下一步只应运行 QMT 自带的 `PY简单示例` 做对照，不再修改或新增 Bridge 代码。

## 内置示例文件比对结论

`PY简单示例_1` 也产生 `parse error`。只读比对两套 QMT 后确认：

| 文件 | 模拟版 | 正式版 |
|---|---:|---:|
| `python\\PY简单示例.py` | 782 字节、单行令牌文本 | 652 字节、正常 Python 源码 |
| `python\\PY简单示例_1.py` | 782 字节、与上项字节完全相同 | 不存在 |

模拟版的两个文件都以 `MmJNMuof...` 形式的一行令牌开始；正式版原始示例以
`#coding:gbk`、`def init(ContextInfo):` 开始。QMT 日志同时记录了模拟版对
`PY简单示例` 的重命名/保存，随后出现 `load file [PY简单示例_1] parse error`。

结论：模拟版当前的“新建/保存/重命名 Python 策略”链路已经把源文件替换为
QMT 无法解析的令牌文本。这是 Bridge 之外的环境问题。原始示例可从正式版
恢复到模拟版，但这是文件覆盖动作，需在用户明确同意后、且先停止相应模拟策略再做。

## 判断修正（后续运行证据）

上述“令牌文本即无法解析”的结论已被后续运行证据否定，保留在本文仅作为当时的
排查记录。2026-09-08 08:52，`KITLING_QMT_API` 使用同类令牌式策略文件，也出现
`CFromulaExpandData::loadFile parse error`，但随后日志仍记录 `PythonFormula construct`
以及 `FormulaOutput` HTTP 服务启动。因此令牌式保存与该解析日志均不能单独用于
判断 Python 策略失败，可能是此版本 QMT 的内部保存/公式解析链路现象。

同一轮中，`PY简单示例_1` 以一分钟周期启动，QMT 完成标的订阅并取得历史 K 线。
这个示例本身没有可观察的 `print` 或业务日志，故没有新增输出也不能证明回调未执行。

后续验收以实际运行副作用为准：`PythonFormula construct`、策略业务日志、Redis
心跳/键，或模拟账户只读查询。不会再只根据文件是否明文、或单独的 `parse error`
判定成功与否。

## 单策略重试结果（09:12）

在停止其他测试策略后，BigQMT 延迟进入 `PythonFormula construct`，并输出
`[bigqmt_signal_trader] init ok`、`get_full_tick=OK` 和持续的调度节拍日志。这证明
Bridge 已在模拟 QMT 内运行，先前观察窗口过短导致误判。

运行诊断显示 RPC 被刻意禁用，因为缺少
`bigqmt_signal_trader_local_config.py`：本地 Redis 配置及账户标识均未加载，Bridge
报告 `rpc_service=NOT STARTED`。这是下一项且唯一需要解决的接入条件；在该配置创建前，
没有 Redis RPC 服务、没有 Redis 业务键，也没有外部订单通道。

同时，`KITLING_QMT_API` 的重新运行已经进入 PythonFormula，但新 HTTP 服务绑定
`127.0.0.1:10085` 时失败，原因是旧服务线程仍占用同一端口。该端口虽仍监听，
但只读版本接口请求超时；它不能作为本次重新启动成功的证据，也不影响 BigQMT 的
模拟 dryrun 验证。
