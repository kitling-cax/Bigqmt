# 统一数据湖 v2 PIT Builder 与 MiniQMT 运行时（2026-09-12）

## PIT Builder

`src/kitling_bigqmt/pit_builder_v2.py` 已加入。它只支持已独立验证的拆分事件路径：从原始价格重建因子，要求 `numeric_status=VERIFIED_SPLIT_RATIO` 和带时区的 `available_at`；现金、配股或未验证累计因子会直接拒绝构建。这样不会把 QMT 诊断 payload 或复权价反推结果写进正式 PIT。

## MiniQMT

`scripts/probe_miniqmt_runtime.py` 确认模拟 QMT 自带 `xtquant` 目录存在，但主机 Python 3.12 无法加载其 cp36-cp39 扩展。MiniQMT 采集器必须运行在 QMT 内置 Python，并把结果以来源事实写入 v2 Bronze；当前探针未抓取数据，未访问券商或订单。

## 当前安全状态

PIT v2 仍为 `BLOCKED_PIT_V2`；全局 `LATEST` 未修改。完整测试达到 110 passed。
