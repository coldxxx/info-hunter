# 批次 1B：来源管理（2026-10-05）

- 来源管理拆成无条件状态controller、详情请求hook与列表/详情/新增/删除/连接视图，app保留default/Source/connectionPlatform入口。
- 共同根section与删除dialog保持挂载；跨页勾选、adding/pending/delete不随详情切换丢失。详情请求键、Abort、focus/Escape、URLpush/replace及连接动作顺序保持。
- 八项原始/拆出JSX与过滤/动作编译AST等价；类型、业务lint、6 API契约和本批格式检查通过。
- 临时副本把其它页面固定在1A基线，再执行两种构建与5组无头交互：筛选/URL/hash/未知参数/刷新；详情直达/刷新/后退/前进；跨页选中及批量关注默认；新增绑定/include_all默认及成功收起；删除失败保留target与dialog、重试成功。无页面错误、外网请求为0，全为合成API数据。
- 未改现有连接筛选谓词、无效详情URL保留等业务行为；真实平台连接继续单独验收。
