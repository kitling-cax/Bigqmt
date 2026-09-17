# Bridge 文件已复制但 QMT 界面不显示：诊断记录

日期：2026-09-08

## 已确认事实

- 三个入口/模块文件存在于模拟版：
  `C:\BigQMT\work\国金QMT交易端模拟\python`
- `bigqmt_signal_trader\` 已在模拟版目录中确认存在，且核心 `.py` 文件完整。
- 正式版目录：
  `C:\BigQMT\work\国金证券QMT交易端\python`
  当前没有这三个文件。
- 当前模拟版磁盘上的文件名已经是：
  - `BIGQMT_REDIS_DRYRUN_1.py`
  - `bigqmt_signal_trader_redis_rpc_runtime_1.py`
  - `bigqmt_signal_trader_strategy_1.py`
- `bigqmt_signal_trader\` 目录仍然存在。
- 模拟版 QMT 配置中的 Python runtime home 指向：
  `C:/BigQMT/work/国金QMT交易端模拟/bin.x64`
- 模拟版日志出现 `configFormula`、`saveIndexPy` 和 `from configFormula`，说明 QMT 界面策略列表使用自己的策略索引/编辑器存储，不是只依赖 Windows 文件夹扫描。

## 原因判断

1. 如果用户当前打开的是正式版 QMT，文件自然不会出现，因为本次只部署到模拟版。
2. 即使打开模拟版，直接把 `.py` 文件放入 `python` 目录也不一定会自动出现在策略列表；需要在 QMT 策略编辑器中“打开/导入/新建后保存”，让 QMT 建立自己的策略索引。
3. QMT 只应加载 `BIGQMT_REDIS_DRYRUN.py`。另外两个 `.py` 是依赖模块，不是独立的可选策略。
4. Bridge 文件复制后，需要刷新策略列表或重启 QMT/模型交易模块；QMT 会缓存已加载模块和策略索引。
5. 运行时还需要整个 `bigqmt_signal_trader\` 包；该包目前已部署到模拟版。只复制三个 `.py` 文件时，加载会因缺少包而失败。
6. `BIGQMT_REDIS_DRYRUN_1.py` 的代码内部仍然导入固定模块名 `bigqmt_signal_trader_strategy` 和 `bigqmt_signal_trader_redis_rpc_runtime`；如果依赖文件也改名为 `_1.py`，运行时会出现模块找不到。QMT 内部策略名称可以叫 `BIGQMT_REDIS_DRYRUN`，但磁盘依赖模块名不能随意改。

## QMT 粘贴保存行为

把代码粘贴到“新建 Python 策略”并保存后，QMT 会把内容写入自己的 `configFormula`/策略索引，策略名称由 QMT 管理；它不保证在 `python` 目录生成同名 `.py` 文件。因此磁盘上没有 `BIGQMT_REDIS_DRYRUN.py`，不代表 QMT 内部策略没有保存。

## 正确加载方式

1. 确认使用模拟版 QMT：
   `C:\BigQMT\work\国金QMT交易端模拟`
2. 进入策略编辑器/模型交易，不要直接运行 `bigqmt_signal_trader_redis_rpc_runtime.py`。
3. 新建或打开一个 Python 策略，将入口设为：
   `BIGQMT_REDIS_DRYRUN.py`
4. 保存、编译，让 QMT 将策略加入自身索引。
5. 在模型交易页面选择该策略，先用模拟信号模式；不要勾选“启动本地 Python”。
6. 观察输出是否出现 `init ok` 和 Redis RPC 启动信息。

当前不把文件复制到正式版，也不修改正式版策略索引。
