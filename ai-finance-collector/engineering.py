"""Explainable developer relevance based on available title/summary evidence.

This is a precision-oriented rule filter, not semantic or factual verification.
Brand names, URLs, the words agent/AI, and source reputation alone never qualify.
"""
import re

VERSION = 1
CATEGORIES = ['工具更新', '工程实践', '开源项目', '评测与性能', '安全与可靠性', '模型与研究']
SEARCH_TERMS = ['API', 'SDK', 'CLI', 'MCP', 'code', 'developer', 'benchmark', 'framework', 'debugging', '开源', '代码', '开发', '评测', '部署', '架构', '上下文']

PATTERNS = {
    '接口与开发组件': r'\b(?:apis?|sdk|cli|ide|mcp|rest|graphql|webhooks?|compiler|linter|runtime|debugger|package manager|model context protocol|codebase|code review|pull requests?|repository|css(?:-in-js)?|test automation|ci/cd|installation tokens?|access tokens?|operating system|open framework|robotics development|vector (?:dbs?|database)|rag)\b|接口|代码库|代码审查|编译器|编程语言|开发框架|代码示例|测试自动化|向量数据库|检索增强|ツール呼び出し|ライブラリ|サンプルコード|코드 리뷰|개발 프레임워크',
    '工程机制': r'\b(?:sandboxes?|sandboxing|tool calling|tool calls?|context (?:engineering|window|management)|system prompts?|agent harness|coding harness|harness|agent memory|memory management|observability|tracing|self.host(?:ed|ing)?|single.gpu deployment|reusable cloud environments?|durable execution)\b|工具调用|上下文(?:工程|管理|窗口)|系统提示词|沙箱|自托管|本地部署|单卡部署|智能体记忆|记忆管理|检查点|断点续跑|システムプロンプト|サンドボックス|ローカル実行|컨텍스트|샌드박스|도구 호출',
    '开源实现': r'\b(?:open[ -]sourc(?:e|ed|es|ing)|open framework|source code|sample code|reference implementation|github repo)\b|开源|源码|参考实现|オープンソース|ソースコード|오픈소스|소스 코드',
    '技术评测': r'\b(?:benchmarks?|swe.bench|evals?|evaluation (?:suite|harness|dataset)|token efficien(?:cy|t)|latency|throughput|profiling|ablation|regression tests?|site performance|inference cost|coding costs?)\b|基准测试|消融实验|可复现|吞吐量|推理延迟|token\s*效率|评测数据集|评估框架|自定义评估|回归测试|ベンチマーク|評価データ|벤치마크|추론 지연',
    '安全细节': r'\b(?:vulnerabilit(?:y|ies)|cve-\d+|fuzzing|prompt injection|sandbox escape|security advisories|security advisory|permission model|threat modeling|security design considerations)\b|漏洞|模糊测试|提示词注入|沙箱逃逸|权限模型|威胁建模|脆弱性|危険コマンド|취약점|프롬프트 인젝션',
    '模型研究': r'\b(?:reinforcement learning|fine.tuning|reward model(?:ing)?|neuro.symbolic|policy compiler|transformer from scratch|critical training|self.modification|open.weights?|open.weight model|computer use|advanced algorithms)\b|强化学习|微调|奖励模型|神经符号|策略编译器|批判性训练|模型权重|计算机使用|高级算法|強化学習|ファインチューニング|강화학습|파인튜닝',
}
TOOLS = re.compile(r'\b(?:claude code|codex|cursor|copilot|opencode|langgraph|langchain|autogen|kiro|github actions|git(?:\s+\d)|coding agents?|coding assistants?)\b|编程助手|代码生成|AI编程|コーディング|코딩', re.I)
UPDATES = re.compile(r'\b(?:releas\w*|launch\w*|introduc\w*|deprecat\w*|retir\w*|roll\w* out|new (?:fields|features|models|default)|now (?:available|support\w*|interact\w*|can)|public preview|support\w*|improv\w*|upgrad\w*|shipping|plugins?|reusable cloud|computer use|rate limits?|retention|highlights|versions?)\b|发布|推出|新增|新功能|更新|升级|停用|弃用|支持|改进|插件|公开预览|正式上线|可用|料金|リリース|公開|発表|デフォルト|출시|업데이트|지원', re.I)
PRACTICE = re.compile(r'\b(?:how (?:to|we|i)|build\w*|implement\w*|debug\w*|deploy\w*|migrat\w*|optimi[sz]\w*|tutorial|walkthrough|postmortem|deep dive|rendering|managing|mastering|from scratch|architecture|technical talks|developer work|developer workflow)\b|如何|实现|构建|架构|实战|原理|排障|调试|教程|优化|实践|渲染|运用|運用|実装|仕組み|チュートリアル|구현|배포|디버깅', re.I)
# Only overt headline intent. Do not blacklist objects such as phones/hotels.
NOISE = {
    '消费导购或营销榜单': r'值不值得买|值得买吗|手机怎么样|选购指南|购机指南|销量|手机.*评测|\bbest (?:phones|smartphones)|\bbuying guide\b',
    '财经、交易或商业收益报道': r'股价|概念股|估值|融资|收购|投资分析|资本市场工具|销售增长|(?:解决|处理).*客户来电|客户来电.*(?:%|％)|\b(?:raises? (?:\$|usd)|funding|acquisition|stock price|shares (?:rise|fall)|wall street|lands? \$|capital markets? tools?)\b',
    '宏观趋势与管理观点': r'结构性转折|市场潜力|治理框架|\b(?:operating model|erp leaders|market outlook|governance framework|agentic transformation)\b',
    '传闻猜测': r'\b(?:leaked|rumou?rs?)\b|传闻|爆料',
    '商务、招聘或活动宣传': r'签署.*协议|合作协议|金牌会员|国标立项|大赛.*颁奖|议程来袭|学术交流会|\b(?:hackathon)\b|\b(?:starts hiring|partnership|collaborations?|conference launches|investments?:)\b',
}
COMPILED = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}


def clean(text):
    text = re.sub(r'https?://\S+', ' ', text or '')
    text = re.sub(r'The post .*? appeared first on .*?(?:\.|$)', ' ', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()


def assess(article, text=None):
    title = clean(article.get('title', ''))
    evidence_text = clean(text if text is not None else title + ' ' + (article.get('excerpt') or ''))
    evidence = [name for name, pattern in COMPILED.items() if pattern.search(evidence_text)]
    headline_evidence = [name for name, pattern in COMPILED.items() if pattern.search(title)]
    tool = bool(TOOLS.search(evidence_text))
    update = bool(UPDATES.search(evidence_text))
    practice = bool(PRACTICE.search(evidence_text))
    if tool and re.search(r'custom workflows|自定义工作流', evidence_text, re.I):
        evidence.append('工程机制')
    # Engineering examples about shopping/finance are allowed when the headline
    # itself describes a concrete implementation; generic success stories are not.
    implementation = bool(PRACTICE.search(title)) and any(x in headline_evidence for x in ('接口与开发组件', '工程机制', '技术评测', '安全细节', '模型研究'))
    for reason, pattern in NOISE.items():
        if re.search(pattern, title, re.I) and not implementation:
            return {'eligible': False, 'category': '', 'reason': reason, 'evidence': evidence}
    core = any(x in evidence for x in ('工程机制', '技术评测', '安全细节', '模型研究'))
    interface = '接口与开发组件' in evidence
    concrete_interface = interface and (update or practice or len(evidence)>1 or bool(re.search(r'show hn|operating system|architecture|架构', title, re.I)))
    project = '开源实现' in evidence and bool(re.search(r'\b(?:model|framework|library|software|code|coding|agent|agentic|robotics)\b|模型|软件|代码|智能体|開発', evidence_text, re.I))
    core = core or concrete_interface
    if not core and not project and not (tool and update):
        return {'eligible': False, 'category': '', 'reason': '标题与摘要缺少具体开发内容', 'evidence': evidence}
    if '安全细节' in evidence:
        category = '安全与可靠性'
    elif '技术评测' in evidence:
        category = '评测与性能'
    elif UPDATES.search(title) and ('接口与开发组件' in evidence or tool) and not PRACTICE.search(title):
        category = '工具更新'
    elif '模型研究' in evidence and not any(x in evidence for x in ('接口与开发组件', '工程机制')):
        category = '模型与研究'
    elif '开源实现' in evidence:
        category = '开源项目'
    elif '工程机制' in evidence or practice:
        category = '工程实践'
    else:
        category = '工具更新'
    if not evidence:evidence = ['开发工具功能变化']
    return {'eligible': True, 'category': category, 'reason': '开发线索：' + '、'.join(evidence[:3]), 'evidence': evidence}
