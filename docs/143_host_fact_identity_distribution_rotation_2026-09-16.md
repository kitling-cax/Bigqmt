# 143 · Host Agent 事实身份分发与轮换

日期：2026-09-16  
状态：本地实现与测试通过；没有生成真实项目密钥；`.121` 未启用事实接收。

## 材料分离

Host Agent 有两类完全不同的材料：

1. **账户执行授权 Key**：模拟/正式账户分开，决定账户是否具有未来执行候选资格；
2. **事实传输身份 Secret**：证明某台 Host Agent 可以向 Coordinator 上报运行事实，不授予下单或 Lease 权限。

事实 Secret 文件由 `scripts/coordinator/manage_fact_identity.py` 生成到服务/容器 Secret 目录，路径不得位于项目树、NAS release 或镜像内。脚本只打印 `host_id/key_id`，不打印 `secret_b64`；Linux 使用 `0600`，Windows 目标环境必须使用仅服务账户可读的 ACL。

## 轮换流程

```text
生成新 key (NEXT)
    ↓
Coordinator Secret 同时信任旧 ACTIVE + 新 NEXT
    ↓
Host Agent 切换到新 key，连续验证事实上传
    ↓
旧 key 标记 REVOKED 并从 trusted 集合移除
    ↓
保留审计记录，不删除历史事件
```

轮换期间允许同一 Host Agent 的两个 key 并行，但同一个 `key_id` 不能映射到不同主机。撤销后旧签名即使时间窗有效也拒绝。账户执行授权 Key 的冲突锁定规则不因事实 Secret 轮换而改变。

## 网络启用前门禁

- `.121` 通过受保护文件挂载 `BIGQMT_FACT_TRUSTED_HOSTS_FILE`；不使用普通环境变量传 secret；
- TLS/内网访问边界、Host ID 与 key ID 白名单完成；
- request ID replay 表、60 秒时间窗、body hash、事件类型白名单通过；
- Shadow `18666` 先验证签名事实接收，且任何响应都保持 `facts_only=true/orders_enabled=false`；
- 生产 `18443` 和正式账户不因事实接收而获得任何订单能力。

本轮新增 Secret 文件解析/轮换测试，和之前认证事实测试一起全量 `259 passed`。详见 `src/kitling_bigqmt/host_fact_identity.py`、`src/kitling_bigqmt/coordinator_fact_auth.py`。
