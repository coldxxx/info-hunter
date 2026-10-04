# 批次 0：安全与回退基线（2026-10-05）

- 保留 LICENSE 初始提交 `a1a2b6f`，首次代码提交为 `317f3a3`（`first-commit`），标签 `baseline/first-commit`。未改写历史、未推送远端。
- 242 个源码/配置/测试/字体和工具说明文件入库。新增根 `.gitignore`、`.dockerignore`；数据库、历史备份、私有配置、账号登录状态、许可密钥、原始 verification 和构建缓存不入 Git/镜像上下文。
- 候选与暂存路径检查通过；常见 token/私钥特征扫描无命中。测试中用于拒绝凭据 URL 的虚构样本保留。扫描不能证明一切敏感内容均不存在，后续新增配置继续逐项审核。
- 78 个数据库/备份/关键配置文件留在原地并在私有临时目录记录内容指纹，验收后比较。没有初始化或运行真实数据库、移动运行实例、修改 LaunchAgent 或重建本机环境。

## 验证基线

- Python 3.9.6：181 个现有 unittest 通过。原受限环境有 34 个 loopback 绑定 PermissionError；在批准的隔离执行环境全部通过，归因于环境限制。
- Node 24.21.0：TypeScript 和 app/lib 的 lint 通过；`build:container`、`build` 在临时副本通过。
- `npm run lint` 有 19 个既有错误，分布在 12 个 UI/hook 文件：breadcrumb、button-group、carousel、chart、field、input-group、input-otp、item、label、pagination、spinner、use-mobile。结构批次不禁用规则或捎带修复。
- Vinext 的路由静态分类 Unknown 是既有构建提示，构建退出码为 0。
- 原始历史手册和迁移前 README 由后续文档批次明确标注其环境与证据范围。
