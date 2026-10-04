# 批次 4：存储与归档入口（2026-10-05）

- 新增 database 管连接配置/初始化，archive_store 管资料入库/备份；radar保留connect/init/put/backup旧入口，以当前DB/ROOT及函数动态传参。
- 函数体与原实现AST等价（参数名替换除外）；schema初始化顺序、旧数据迁移前备份、WAL/secure_delete、SQL、收藏/笔记/核验恢复、Reddit备份清理及语义重建不变。
- Docker继续复制根级Python模块；无数据库迁移、新表或配置改动。
- 接入后 `python3 scripts/check_backend.py`：185项完整测试通过（24.555秒），用临时数据库、备份、连接配置和原生目录。
- 剩余：radar中的路由与调度将在下一批通过窄依赖契约整理。
