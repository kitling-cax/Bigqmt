# BigQMT 隔离 Raw 入库回读验证（2026-09-12）

## 结论

`bigqmt_candidate_20260912_145717` 已按显式批准完成 copy-on-write 入库，并通过发布后回读验证。目标是数据湖 Bronze 下的独立 release，不合并、不覆盖旧 `bronze/bars_raw`，也没有更新全局 `catalog/LATEST.json`。

## 发布位置

- Release：`C:\BigQMT\research\quant_data_lake\bronze\_bigqmt_raw_releases\bigqmt_candidate_20260912_145717`
- Manifest：同目录 `publish_manifest.json`
- 验证证据：`runtime_data/evidence/simulation/raw_publish/bigqmt_candidate_20260912_145717_verification.json`
- Tree hash：`7bc6aa7f0bf5309ecd11050d1987bc620ae5128d6f371b2907fe7a1e02dc2375`

## 回读结果

| 数据集 | 源候选行数 | 发布后行数 | 标的数 | 业务键回读 | 行哈希回读 | Raw/OHLC/单位 |
|---|---:|---:|---:|---|---|---|
| 日线 `1d` | 22,218 | 22,218 | 31 | 通过 | 通过 | `adjustment_mode=none`，通过 |
| 分钟 `1m/5m` | 35,836 | 35,836 | 31 | 通过 | 通过 | `adjustment_mode=none`，通过 |

补充检查：两类数据均无重复业务键、无重复行哈希、无空 OHLCV、OHLC 关系正确、成交量和成交额非负；发布树哈希与 manifest 一致；staging 目录已清理。

## 安全边界

- `bronze/bars_raw`：未修改。
- `catalog/LATEST.json`：未修改；全局版本仍不切换。
- Silver/PIT：仍阻断，原因是 canonical factor chain 与精确 `available_at` 尚未完成验证。
- 正式账户：保持只读。
- 本次过程：未调用 QMT/Redis 下单、撤单或其他券商写操作。

## 后续

该 release 现在可作为 BigQMT Raw overlay 的稳定输入，供只读 DuckDB 扫描和后续质量处理使用。只有 PIT 因子链、单位和 `available_at` 证据完整后，才能另行生成 Silver/PIT release；不得把本次 Raw release 误标为全局 `LATEST`。

Dashboard 的模拟盘 `/api/status` 已增加只读 `bigqmt_raw_release` 投影，显示 release 状态、日线/分钟线行数、tree-hash/roundtrip 门禁和 PIT 阻断原因；接口验证通过且订单开关仍为关闭。
