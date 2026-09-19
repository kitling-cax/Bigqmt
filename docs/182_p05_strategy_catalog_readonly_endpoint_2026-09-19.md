# P05 策略 candidate 只读目录接口（2026-09-19）

新增 `GET /api/v1/strategy-candidates`，扫描 Coordinator 配置的策略库目录。

默认路径：

- Windows 本地：项目根 `releases/strategies`
- Linux Coordinator：`/var/lib/kitling-bigqmt-coordinator/strategy-library`
- 部署时可用 `BIGQMT_STRATEGY_LIBRARY_ROOT` 指向本机挂载的 NAS 私有策略库

接口逐个读取 `MANIFEST.json`，校验所有 artifact 的 SHA-256，并只返回：策略 ID、版本、构建号、Bridge RPC 版本、构件数量、Manifest 哈希和 `READY/INVALID` 状态。

安全边界：

- `readonly=true`；
- `orders_enabled=false`；
- `push_supported=false`；
- `install_supported=false`；
- 不创建 Assignment、不下载文件、不调用 Windows 托盘、不获得执行租约。

当前网页端仍是只读 Fleet 页面，尚未提供“推送/安装”按钮。下一阶段才增加推送预览：网页选择 candidate 和目标主机，Coordinator 生成不可执行的 Assignment Preview；由目标 Host Agent 在本机校验哈希并由托盘确认安装。策略源码仍只放 NAS 私有库，不进入 GitHub。
