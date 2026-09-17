# QMT_LOGGING_PROBE 使用说明

此文件是参照已成功运行的 `KITLING_QMT_API.py` 写的最小 QMT 生命周期探针。

- 仅使用 `logging`；QMT 将其写入 `XtClient_FormulaOutput_YYYYMMDD.log`。
- 不导入 Redis，不访问账户、持仓、委托或成交，不调用任何下单函数。
- 不启动 HTTP 服务、后台线程或额外行情订阅。

在模拟 QMT 中使用时：先停止 `BIGQMT_REDIS_DRYRUN`，新建名称为
`QMT_LOGGING_PROBE` 的 Python 策略，完整粘贴本文件内容，设置 `SH000300`、一分钟线，
且只运行这一个策略。

通过标准：日志同时出现 `PythonFormula construct` 与
`[qmt_logging_probe] init ok`。在此之前不要继续加载 BigQMT Bridge。
