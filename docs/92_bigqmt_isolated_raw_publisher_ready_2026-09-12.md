# BigQMT 隔离 Raw 发布器就绪

日期：2026-09-12。

此前候选包已经通过字段、单位、OHLC、重复键和本地分区回读，但没有正式发布器。本轮新增：

`scripts/publish_bigqmt_raw_overlay.py`

## 发布器行为

- 默认运行只读校验，返回 `READY_FOR_EXPLICIT_RAW_PUBLISH`；不会写共享湖。
- 校验候选 manifest、`raw_bronze_import_ready`、行数、业务键、行哈希、Raw `adjustment_mode=none`、OHLC 和非负量额。
- 使用 copy-on-write，目标是 `bronze/_bigqmt_raw_releases/<release_id>`，保留日线 `year/period` 和分钟线 `year/month/period` 分区。
- 目标版本已存在时只接受相同 manifest 的 `DUPLICATE`，不覆盖任何文件。
- 永不写旧 `bronze/bars_raw`，永不修改 `catalog/LATEST.json`，永不发布 Silver/PIT。
- 只有显式 `--approve-raw-publish` 才会执行隔离 Raw 写入；该参数不包含任何交易权限。

## 当前验证

- `py -m pytest -q`：75 项通过。
- 最新候选包：22,218 条日线、35,836 条 1m/5m；31 个标的；6,260 条上市前占位已隔离。
- `py scripts/publish_bigqmt_raw_overlay.py`：`READY_FOR_EXPLICIT_RAW_PUBLISH`，`lake_write=false`。
- 临时湖发布单元测试验证了错误 token、重复发布、隔离目录、旧表不变和 OHLC 失败关闭。

## 尚未执行的动作

本轮没有写入 `C:\BigQMT\research\quant_data_lake`，也没有更新 `LATEST`。如果确认发布，只需对指定 release 运行独立发布命令；PIT/Silver 仍因 canonical factor 与 `available_at` 证据不足保持阻断。
