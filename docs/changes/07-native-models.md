# 批次 7：模型请求与本机服务边界（2026-10-05）

- `translation_model.py` 承接原始 completions 请求与数字占位保护；translation 保留队列、缓存和公共包装，在调用时传入当前 model/protect_numbers。提示词、端点、分块、代理绕过及失败条件保持。
- native 新增 state、wechat_bridge、media_api。service 保留认证、Origin、异常、lifespan 和路由包装；token/root 权限、WAL、缓存桥接、上传清理及 512 MB 边界保持。新边界模块导入本身不初始化私有目录。
- 抽取函数与初始化序列通过 AST 等价审查。没有重建迁移来的虚拟环境、修改 LaunchAgent、启动真实 worker 或切换实例。

## 验证

- 翻译现有 6 项针对性检查通过；完整核心回归在 Python 3.9.6 / 3.12.12 各 185 项通过。
- 新增 native 的 11 项隔离检查，通过 `scripts/check_native.py` 运行。覆盖认证/Origin、token 权限与复用、健康/连接、上传转交/空文件/超限及临时清理、公共媒体 DNS 校验和私网拒绝、公众号缓存参数/禁用代理/拒绝目的地与重定向。
- native 用实际迁移 Python 3.12.12 与现有依赖；ASGITransport 不启动 lifespan，目录全在临时空间，DNS/桥接/任务提交用替身。实际平台、浏览器登录、模型效果与跨进程恢复未据此验收。
- 后端独立只读审查未发现本次行为、安全或部署回归；Docker 根级 COPY 覆盖新增模块。

准确命令和最终集成结果见 [总验收](08-acceptance.md)。旧 native 绝对链接仍失效，运行准备按 [运维说明](../operations.md) 单独安排。
