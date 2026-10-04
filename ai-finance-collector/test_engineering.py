import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit,quote
import engineering
import radar
import watchlists
import test_radar
import test_http

BAD_TITLES = [
    'AI智能体预订酒店机票节省10%成本旅游平台股价承压- AI - 亿邦动力',
    '努比亚手机怎么样？2026年真全面屏+AI智能体双线评测，3个维度说清值不值得买+FAQ - 手机新浪网',
    'Proaction 借助 Codex 实现销售增长 60%，节省超 75 小时 - OpenAI',
    'Chatham Financial 使用 OpenAI Codex 构建资本市场工具',
    'Muse加速智能体商业化叙事 AI决策概念股深演智能三日累涨60%',
    'The Consumer AI Agent Race: Five Platforms, Three Pricing Models, One Winner',
    'Scale AI Lands $12M Air Force Deal for Agentic AI',
    'MCP Is Becoming the Plumbing of Agentic ERP—ERP Leaders Need to Understand It',
    'Cursor一夜干掉了GitHub',
    'Model Context Protocol Server and AI Agent Government Hackathon',
    '如何用 AI Agent 预订酒店节约旅行费用',
    'Is Google Canceling Gemini? Leaked SDK Code Reveals AGENTIC Shift',
]
GOOD_TITLES = [
    'Copilot code review: API support and new default effort level',
    'Selected models in GitHub Copilot deprecated',
    'Stateless GitHub App installation tokens rolled out',
    'GitHub Actions: macOS 14 runner image retirement',
    'Graphify：整合代码库上下文，优化基于代理的软件工程',
    'Show HN: RepoGuard – Architecture linter for AI-generated code (Cursor, Claude)',
    '如何用 MCP SDK 实现酒店预订 Agent：接口设计与失败重试',
    '手机端 AI Agent 开发实战：Android SDK 与本地部署',
    'AI智能体股价分析工具的开源实现：API 限流与回归测试',
    'Improving site performance by shipping more CSS',
    'How we found 24 Android vulnerabilities using our open source AI security agent',
    'MCP サーバー開発：SDK とサンプルコードを公開',
    '에이전트 SDK 출시와 도구 호출 구현',
    'AI Agent Reinforcement Learning: reference implementation',
    'Orchard: An open framework for scalable agentic AI',
    'FTL: A new operating system for clouds',
]

class EvidenceTests(unittest.TestCase):
    def test_real_noise_and_counterexamples(self):
        for title in BAD_TITLES:
            with self.subTest(title=title):self.assertFalse(engineering.assess({'title':title,'excerpt':title})['eligible'])
        for title in GOOD_TITLES:
            with self.subTest(title=title):self.assertTrue(engineering.assess({'title':title,'excerpt':''})['eligible'])

    def test_urls_brands_and_generic_agent_do_not_create_evidence(self):
        a={'title':'AI agents for every family','excerpt':'https://github.com/example/sdk-api-code-review https://example.org/tutorial'}
        self.assertFalse(engineering.assess(a)['eligible'])
        self.assertFalse(engineering.assess({'title':'Next era of Cursor and Codex'})['eligible'])

    def test_summary_can_supply_missing_technical_detail(self):
        a={'title':'Agent sessions, revisited','excerpt':'We implement durable execution and checkpoint recovery, with sample code.'}
        decision=engineering.assess(a)
        self.assertTrue(decision['eligible']);self.assertIn(decision['category'],engineering.CATEGORIES)
        self.assertIn('工程机制',decision['evidence'])

class RelevanceTests(unittest.TestCase):
    setUp=test_radar.RadarTests.setUp
    tearDown=test_radar.RadarTests.tearDown

    def add(self,c,title,suffix):
        source={'id':'coding-github','name':'Test','region':'全球','language':'en','kind':'新闻'}
        radar.put(c,source,{'url':'https://example.com/'+suffix,'title':title,'excerpt':'','published_at':None})
        return c.execute('SELECT id FROM articles WHERE url=?',('https://example.com/'+suffix,)).fetchone()[0]

    def test_collection_and_archive_use_same_gate_even_with_include_all(self):
        with radar.connect() as c:
            t=watchlists.get(c,'coding-agent')
            for title in BAD_TITLES:
                self.assertIsNone(watchlists.applies(t,{'title':title},title,include_all=True))
            s=next(s for s in watchlists.collection_sources(c,'coding-agent') if s['id']=='coding-github')
            feed=[{'title':title,'excerpt':'','url':'https://example.com/'+str(i)} for i,title in enumerate(BAD_TITLES+[GOOD_TITLES[0]])]
            with patch.object(radar,'fetch',return_value=b'feed'),patch.object(radar,'parse_feed',return_value=feed):
                rows,status,_=radar.collect_source(s)
            self.assertEqual(status,'成功');self.assertEqual([a['title'] for a in rows],[GOOD_TITLES[0]])
            for i,a in enumerate(feed):self.add(c,a['title'],str(i))
            watchlists.reindex(c,'coding-agent')
            self.assertEqual(c.execute("SELECT count(*) FROM article_watches WHERE topic_id='coding-agent'").fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM articles').fetchone()[0],len(feed))

    def test_migration_preserves_originals_ai_membership_and_explicit_choice(self):
        with radar.connect() as c:
            ids=[self.add(c,BAD_TITLES[0],'bad'),self.add(c,GOOD_TITLES[0],'good')]
            for aid in ids:
                c.execute('INSERT OR REPLACE INTO article_watches VALUES(?,?,?)',(aid,'coding-agent','关键词：智能体'))
                c.execute('INSERT OR REPLACE INTO article_watches VALUES(?,?,?)',(aid,'ai','原AI资料库'))
            c.execute("UPDATE articles SET note='Keep my note',starred=1,review='存疑'")
            before=[tuple(r) for r in c.execute('SELECT * FROM articles ORDER BY id')]
            t=watchlists.get(c,'coding-agent');t.pop('content_profile');t['regions']=['中国大陆']
            c.execute('UPDATE watch_topics SET config=? WHERE id=?',(json.dumps(t),'coding-agent'))
            c.execute('DELETE FROM watch_migrations')
            watchlists.bootstrap(c,radar.AI_WORDS)
            self.assertEqual(watchlists.get(c,'coding-agent')['regions'],[])
            self.assertEqual([r[0] for r in c.execute("SELECT article_id FROM article_watches WHERE topic_id='coding-agent'")],[ids[1]])
            self.assertEqual(c.execute("SELECT count(*) FROM article_watches WHERE topic_id='ai'").fetchone()[0],2)
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM articles ORDER BY id')],before)
            watchlists.save(c,{'id':'coding-agent','content_profile':'standard'})
            watchlists.bootstrap(c,radar.AI_WORDS)
            self.assertEqual(watchlists.get(c,'coding-agent')['content_profile'],'standard')

    def test_manual_import_and_general_topics_remain_available(self):
        with radar.connect() as c:
            aid=self.add(c,BAD_TITLES[0],'manual')
            c.execute('INSERT INTO article_watches VALUES(?,?,?)',(aid,'coding-agent','手动收录'))
            watchlists.reindex(c,'coding-agent')
            self.assertEqual(c.execute("SELECT reason FROM article_watches WHERE topic_id='coding-agent'").fetchone()[0],'手动收录')
            t=watchlists.save(c,{'name':'旅行','keywords':'酒店','news_search':False})
            self.assertEqual(c.execute('SELECT count(*) FROM article_watches WHERE topic_id=?',(t['id'],)).fetchone()[0],1)

    def test_profile_configuration_and_search_are_persistent(self):
        with radar.connect() as c:
            t=watchlists.save(c,{'id':'coding-agent','regions':['韩国'],'content_profile':'developer'})
            self.assertEqual(t['regions'],[])
            s=json.loads(c.execute("SELECT config FROM sources WHERE id='search-coding-agent-US'").fetchone()[0])
            query=parse_qs(urlsplit(s['url']).query)['q'][0]
            self.assertIn('(API OR SDK',query)
            self.assertIn('英文技术检索',s['name'])
            with self.assertRaises(ValueError):watchlists.save(c,{'id':'coding-agent','content_profile':'invalid'})

class DirectionHttpTests(unittest.TestCase):
    setUp=test_http.HttpTests.setUp
    tearDown=test_http.HttpTests.tearDown
    request=test_http.HttpTests.request
    def test_direction_filter_and_profile_api(self):
        with radar.connect() as c:
            source={'id':'coding-github','name':'Test','region':'日本','language':'en','kind':'新闻'}
            for i,title in enumerate([GOOD_TITLES[0],GOOD_TITLES[9],BAD_TITLES[0]]):
                radar.put(c,source,{'url':'https://example.com/api/'+str(i),'title':title,'excerpt':'GitHub','published_at':None})
        result=self.request('articles?watch_id=coding-agent&engineering_category='+quote('工具更新'))
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['engineering_category'],'工具更新')
        self.assertEqual(self.request('articles?watch_id=coding-agent')['total'],2)
        self.assertEqual(self.request('articles')['total'],3)
        result=self.request('watch-topic',{'id':'coding-agent','content_profile':'standard'})
        self.assertEqual(result['content_profile'],'standard')
        with self.assertRaises(Exception):self.request('articles?watch_id=coding-agent&engineering_category='+quote('工具更新'))
