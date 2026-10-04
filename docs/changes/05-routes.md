# 批次 5：来源与资料 API 边界（2026-10-05）

- source_api 接管来源库/详情、主题、关注批量、来源添加/反馈/软删除；article_api 接管查询、笔记核验与手动导入。Handler保留HTTP解析、Host/Origin校验、异常边界和静态文件。
- api_contracts 使用小型 RouteResult 与调用时创建的 Source/Article/CollectionServices；collection_api不再接收整个radar模块。保留动态fetch/parse_feed/canonical/put/date测试替换。
- 13个原分支与新实现AST等价（send转RouteResult及函数参数注入除外），状态码、SQL、校验次序与事务保持；网络发现仍在写事务外。
- `python3 scripts/check_backend.py`：185项完整测试通过（24.625秒），隔离DB/备份/私有目录。
- 无API路径/响应结构/新表变化；原GET异常处理边界保留，未捎带错误策略变更。
