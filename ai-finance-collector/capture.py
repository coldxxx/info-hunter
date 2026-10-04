"""Reusable capture strategies; sources supply parameters, never topic-specific code."""
from dataclasses import dataclass
from typing import Callable
import social
import native_client


@dataclass(frozen=True)
class Adapter:
    strategy: str
    name: str
    read: Callable
    parameters: tuple[tuple[str, str], ...]


STRATEGIES = {
    'isolated-browser': {'name':'隔离浏览器','description':'本机独立配置目录，串行低频读取；验证码与登录失效暂停等待人工处理。','automatic':True},
    'wechat-bridge': {'name':'公众号桥接','description':'读取本机 We-MP-RSS 缓存，不触发重复上游采集。','automatic':True},
    'public-feed': {'name': '公开订阅', 'description': '共用 RSS / Atom / RDF 读取与解析。论坛、博客、新闻和频道只需提供订阅入口。', 'automatic': True},
    'official-api': {'name': '官方 API', 'description': '共用授权检查、请求额度、限流与结果记录；平台适配器负责接口、分页边界和帖子字段映射。', 'automatic': True},
    'assisted-import': {'name': '浏览器辅助', 'description': '共用人工读取与导入流程；平台适配器校验帖子链接和字段。定时任务不会自动打开浏览器。', 'automatic': False},
    'manual-import': {'name': '手动录入', 'description': '共用链接与摘录录入流程。没有可用自动入口的来源保留配置，等待接入。', 'automatic': False},
}


def _feed(source, context):
    import feed_reader
    return feed_reader.read(source,context)


def _api(source, context):
    return social.collect(source, context['db'])


def _browser(source, context):
    return [], '浏览器辅助', source.get('note', '需手动触发网页读取')


def _manual(source, context):
    return [], '待接入', source.get('note', '需要账号或手动导入')


def _automatic_browser(source,context):
    try:
        result=native_client.call('/v1/browser/collect',source,timeout=180)
        return result['rows'],result['status'],result.get('error','')
    except ValueError as e:return [],'执行器未连接',str(e)

def _wechat(source,context):
    try:
        raw=native_client.call('/v1/wechat/feed',{'url':source['bridge_feed']})['feed']
        return context['parse_feed'](raw.encode()),'成功',''
    except ValueError as e:return [],'公众号待检查',str(e)

ADAPTERS = {
    'rss-browser': Adapter('public-feed','RSS + 会员正文',_feed,(('订阅地址','feed_url'),('正文连接','connection_id'))),
    'browser-auto': Adapter('isolated-browser','隔离浏览器',_automatic_browser,(('网页入口','url'),('连接','connection_id'))),
    'wechat-rss': Adapter('wechat-bridge','We-MP-RSS',_wechat,(('公众号入口','url'),('本机订阅','bridge_feed'))),
    'rss': Adapter('public-feed', 'RSS / Atom', _feed, (('订阅地址', 'feed_url'),)),
    'reddit': Adapter('official-api', 'Reddit API', _api, (('板块', 'subreddit'),)),
    'x': Adapter('official-api', 'X API', _api, (('检索条件', 'query'),)),
    'browser': Adapter('assisted-import', '浏览器辅助', _browser, (('网页入口', 'url'),)),
    'manual': Adapter('manual-import', '手动 / 待接入', _manual, (('来源入口', 'url'),)),
}


def describe(source, settings=None):
    ident = social.effective_adapter(source, settings)
    adapter = ADAPTERS.get(ident)
    if not adapter:
        raise ValueError('未支持的采集适配器：' + ident)
    parameters = [{'label': label, 'value': source.get(key) or (source['url'] if key == 'feed_url' else '')} for label, key in adapter.parameters]
    return dict(STRATEGIES[adapter.strategy], id=adapter.strategy, adapter=ident, adapter_name=adapter.name, parameters=parameters)


def read(source, *, fetch, parse_feed, db):
    ident = social.effective_adapter(source)
    adapter = ADAPTERS.get(ident)
    if not adapter:
        raise ValueError('未支持的采集适配器：' + ident)
    # All adapters return the same candidate fields: title, URL, excerpt, date, publisher.
    # The caller then applies shared topic rules, deduplication, and archiving.
    return adapter.read(dict(source, adapter=ident), {'fetch': fetch, 'parse_feed': parse_feed, 'db': db})
