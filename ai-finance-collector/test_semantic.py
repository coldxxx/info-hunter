import array
import json
import math
import unittest
from unittest.mock import patch
import content_store
import dedup
import radar
import semantic as s
import semantic_models as m
import test_radar
import test_http
import test_dedup


def decision(a, b, relation='duplicate'):
    return dict(relation=relation, same_event=relation in ('duplicate', 'complement', 'conflict'),
                new_information=relation == 'complement', contradiction=relation == 'conflict',
                sufficient_evidence=True, confidence=0.99, reason='同一公告，无新增信息',
                evidence_a=a['title'], evidence_b=b['title'])


class ModelValidation(unittest.TestCase):
    def setUp(self):
        self.a = dict(title='GitHub releases a new code review API', excerpt='The company announced code review through the REST and GraphQL APIs for existing subscribers.')
        self.b = dict(self.a, title='Code review API released by GitHub')

    def test_numeric_conflict_missing_quote_and_contradictory_decisions_are_not_duplicates(self):
        a, b = dict(self.a, title=self.a['title'] + ' v2'), dict(self.b, title=self.b['title'] + ' v3')
        self.assertEqual(m.validate(decision(a, b), a, b)['relation'], 'uncertain')
        d = decision(self.a, self.b); d['evidence_b'] = 'Invented proof not present in source'
        self.assertEqual(m.validate(d, self.a, self.b)['relation'], 'uncertain')
        d = decision(self.a, self.b); d['new_information'] = True
        self.assertEqual(m.validate(d, self.a, self.b)['relation'], 'uncertain')

    def test_truncated_text_and_title_only_require_review(self):
        a = dict(self.a, body='long content ' * 700)
        self.assertEqual(m.validate(decision(a, self.b), a, self.b)['relation'], 'uncertain')
        a = dict(self.a, excerpt='')
        self.assertEqual(m.validate(decision(a, self.b), a, self.b)['relation'], 'uncertain')
        self.assertEqual(m.validate(decision(self.a, self.b), self.a, self.b)['relation'], 'duplicate')

    def test_bad_vectors_and_malformed_schema_are_rejected(self):
        for vector in ([0] * 16, [math.nan] * 16, [1] * 3, ['1'] * 16):
            with self.assertRaises(ValueError):m.normalize(vector)
        d = decision(self.a, self.b); d['same_event'] = 'true'
        with self.assertRaises(ValueError):m.validate(d, self.a, self.b)
        with patch.object(m, 'rpc', return_value={'data': [{'index': 2, 'embedding': [1] * 16}]}):
            with self.assertRaises(ValueError):m.embed(m.DEFAULTS, ['article'])

    def test_external_service_and_prompt_fields_rejected(self):
        for url in ('https://api.example.com/v1', 'http://user:password@localhost:1234/v1', 'http://localhost:1234/v1?token=x'):
            with self.assertRaises(ValueError):m.endpoint(url)
        self.assertIn('UNTRUSTED DATA', m.INSTRUCTION)

    def test_qwen_schema_in_reasoning_field_and_escaped_quotes(self):
        d = decision(self.a, self.b)
        d['evidence_a'] = '\\"' + d['evidence_a'] + '\\"'
        with patch.object(m, 'rpc', return_value={'choices':[{'finish_reason':'stop', 'message':{'content':'','reasoning_content':json.dumps(d)}}]}):
            self.assertEqual(m.judge(m.DEFAULTS, self.a, self.b)['relation'], 'duplicate')
        with patch.object(m, 'rpc', return_value={'choices':[{'message':{'content':'','reasoning_content':'Let me think. '+json.dumps(d)}}]}):
            with self.assertRaises(ValueError):m.judge(m.DEFAULTS, self.a, self.b)


class SemanticState(test_radar.RadarTests):
    def put(self, suffix, title=None, body=None):
        source = dict(id='semantic-' + suffix, name='Research '+suffix, region='全球', language='en', kind='新闻')
        row = dict(url='https://example.com/' + suffix, title=title or 'Copilot adds a new code review interface '+suffix,
                   excerpt='Existing subscribers can request code reviews through REST and GraphQL. The feature introduces a review request interface.', published_at='2026-10-02T12:00:00Z')
        if body:row['body'] = body
        with radar.connect() as c:
            radar.put(c, source, row)
            return s.document(c, c.execute('SELECT id FROM articles WHERE url=?', (row['url'],)).fetchone()[0])

    def save(self, c, a, b, relation='duplicate', auto=False):
        cfg = s.settings(c)
        d = m.validate(decision(a, b, relation), a, b)
        s.save_decision(c, a, b, .96, cfg, d)
        pid = s.pair_id(a['id'], b['id'])
        if auto:c.execute("UPDATE semantic_pairs SET status='auto' WHERE id=?", (pid,))
        return pid

    def test_review_split_and_undo_preserve_annotations_and_filtering(self):
        a, b = self.put('a'), self.put('b')
        with radar.connect() as c:
            c.execute("UPDATE articles SET starred=1,note='keep evidence',review='存疑' WHERE id=?", (b['id'],))
            before = [tuple(r) for r in c.execute('SELECT * FROM articles ORDER BY id')]
            pid = self.save(c, a, b)
            event = s.review(c, pid, 'duplicate')['event_id']
            self.assertEqual(dedup.count(c), 1)
            self.assertEqual(dedup.count(c, raw=True), 2)
            self.assertEqual(dedup.page(c, '', [], 0)[0]['id'], b['id'])
            self.assertEqual(dedup.page(c, ' WHERE source_id=?', [a['source_id']], 0)[0]['id'], a['id'])
            self.assertEqual(len(dedup.versions(c, dedup.page(c, '', [], 0)[0]['duplicate_group'])), 2)
            split = s.split(c, b['id'])['event_id']
            self.assertEqual(dedup.count(c), 2)
            s.rebuild(c);self.assertEqual(dedup.count(c), 2)
            s.undo(c, split);self.assertEqual(dedup.count(c), 1)
            s.undo(c, event);self.assertEqual(dedup.count(c), 2)
            self.assertEqual(before, [tuple(r) for r in c.execute('SELECT * FROM articles ORDER BY id')])

    def test_stale_body_invalidates_group_and_outdated_review(self):
        a, b = self.put('a'), self.put('b')
        with radar.connect() as c:
            pid = self.save(c, a, b);s.review(c, pid, 'duplicate')
            content_store.store(c, a['id'], {'body':'New independent measurements contradict the announcement.'})
            self.assertEqual(dedup.count(c), 2)
            self.assertEqual(c.execute('SELECT status FROM semantic_pairs').fetchone()[0], 'stale')
            with self.assertRaises(ValueError):s.review(c, pid, 'duplicate')

    def test_automatic_linkage_does_not_chain_unverified_pairs(self):
        a, b, d = self.put('a'), self.put('b'), self.put('c')
        with radar.connect() as c:
            self.save(c, a, b, auto=True);self.save(c, b, d, auto=True);s.rebuild(c)
            self.assertEqual(dedup.count(c), 2)
            self.save(c, a, d, auto=True);s.rebuild(c)
            self.assertEqual(dedup.count(c), 1)
            s.split(c, b['id']);s.rebuild(c)
            self.assertEqual(dedup.count(c), 2)

    def test_model_failure_retry_budget_and_embedding_reuse(self):
        a, b = self.put('a'), self.put('b')
        with radar.connect() as c:cfg = s.configure(c, {'enabled': True, 'daily_pair_limit': 1})
        with patch.object(m, 'embed', return_value=[[.25] * 16] * 2) as embed, patch.object(m, 'judge', side_effect=lambda cfg,a,b:m.validate(decision(a,b),a,b)) as judge:
            self.assertTrue(s.process_one(radar.connect, cfg))
            self.assertTrue(s.process_one(radar.connect, cfg))
            # Remaining jobs complete from the cached pair without another call.
            while s.process_one(radar.connect, cfg):pass
            self.assertEqual(judge.call_count, 1)
            with radar.connect() as c:s.enqueue(c, force=True)
            s.process_one(radar.connect, cfg)
            self.assertEqual(embed.call_count, 1)
        with radar.connect() as c:
            c.execute('DELETE FROM semantic_vectors');s.enqueue(c, force=True)
        with patch.object(m, 'embed', side_effect=ValueError('offline')):
            for _ in range(3):
                s.process_one(radar.connect, cfg)
                with radar.connect() as c:c.execute('UPDATE semantic_jobs SET next_at=0')
        with radar.connect() as c:
            self.assertEqual(s.status(c)['jobs']['failed'], 2)

    def test_auto_gate_is_model_and_threshold_specific(self):
        with radar.connect() as c:
            cfg = s.settings(c)
            with self.assertRaises(ValueError):s.configure(c, {'mode': 'auto'})
            c.execute('INSERT INTO semantic_evaluations(profile,report,created_at) VALUES(?,?,0)', (m.profile(cfg), json.dumps(dict(count=120, negatives=60, precision=1, recall=.9))))
            self.assertTrue(s.auto_gate(c, cfg)['ready'])
            self.assertFalse(s.auto_gate(c, dict(cfg, auto_threshold=.99))['ready'])
            self.assertFalse(s.auto_gate(c, dict(cfg, judge_model='different'))['ready'])

    def test_removal_purges_vectors_pairs_and_rebuilds_remaining_group(self):
        a, b = self.put('a'), self.put('b')
        with radar.connect() as c:
            pid = self.save(c, a, b);s.review(c, pid, 'duplicate')
            c.execute('INSERT INTO semantic_vectors VALUES(?,?,?,?,?,0)', (a['id'],s.fingerprint(a),'model',16,array.array('f',[.25]*16).tobytes()))
            content_store.remove(c, a['id'])
            self.assertEqual(c.execute('SELECT count(*) FROM semantic_pairs').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM semantic_vectors').fetchone()[0], 0)
            self.assertEqual(dedup.count(c), 1)
            event = c.execute('SELECT id FROM semantic_audit LIMIT 1').fetchone()[0]
            with self.assertRaises(ValueError):s.undo(c, event)

    def test_evaluation_rejects_repeated_pairs_before_calling_models(self):
        a, b = self.put('a'), self.put('b')
        with radar.connect() as c, patch.object(m, 'judge') as judge:
            with self.assertRaises(ValueError):s.evaluate(c, s.settings(c), [{'left':a,'right':b,'expected':'duplicate'},{'left':b,'right':a,'expected':'duplicate'}])
            judge.assert_not_called()

    def test_display_order_matches_model_evidence_and_reason(self):
        a,b = sorted((self.put('a'),self.put('b')),key=lambda x:x['id'],reverse=True)
        with radar.connect() as c:
            self.save(c,a,b)
            p=s.pairs(c,{'status':'all'})['items'][0]
            self.assertEqual(p['left']['id'],a['id'])
            self.assertEqual(p['decision']['evidence_a'],a['title'])

    def test_human_labels_survive_model_change_and_reversed_model_input(self):
        a,b = self.put('a'),self.put('b')
        with radar.connect() as c:
            pid=self.save(c,a,b);s.review(c,pid,'complement')
            s.configure(c,{'judge_model':'new-model-revision'})
            self.assertEqual(s.pairs(c,{'status':'reviewed'})['total'],1)
            self.save(c,b,a,'related')
            p=s.pairs(c,{'status':'reviewed','relation':'complement'})['items'][0]
            self.assertEqual(p['reviewed_relation'],'complement')
            self.assertEqual(p['left']['id'],b['id'])
            self.assertEqual(s.status(c)['awaiting'],0)

    def test_original_rule_group_can_be_split_and_undone(self):
        with radar.connect() as c:
            radar.put(c, test_dedup.INDEX_SOURCE, test_dedup.INDEX)
            radar.put(c, test_dedup.DIRECT_SOURCE, test_dedup.ORIGINAL)
            self.assertEqual(dedup.count(c), 1)
            aid = c.execute('SELECT id FROM articles LIMIT 1').fetchone()[0]
            event = s.split(c, aid)['event_id'];self.assertEqual(dedup.count(c), 2)
            s.undo(c, event);self.assertEqual(dedup.count(c), 1)


class SemanticHttp(test_http.HttpTests):
    def test_review_api_topic_isolation_and_cross_site_protection(self):
        with radar.connect() as c:
            radar.put(c, test_dedup.INDEX_SOURCE, test_dedup.INDEX)
            radar.put(c, test_dedup.DIRECT_SOURCE, test_dedup.ORIGINAL)
            rows = [s.document(c,r[0]) for r in c.execute('SELECT id FROM articles')]
            s.save_decision(c,*rows,.95,s.settings(c),m.validate(decision(*rows),*rows))
        pairs = self.request('semantic/pairs?watch_id=coding-agent')['items']
        self.assertEqual(len(pairs), 1)
        self.assertEqual(self.request('semantic/pairs?watch_id=ai')['items'], [])
        self.request('semantic/review', dict(pair_id=pairs[0]['id'],relation='complement',expected=pairs[0]['updated_at']))
        self.assertEqual(self.request('articles')['total'], 2)
        self.assertEqual(self.request('semantic/pairs?status=reviewed')['total'], 1)
        self.assertEqual(self.request('semantic/pairs?status=reviewed&relation=complement')['total'], 1)
        self.assertEqual(self.request('semantic/pairs?status=reviewed&relation=duplicate')['total'], 0)
        event = self.request('semantic/status')['events'][0]['id']
        self.request('semantic/undo', {'event_id':event})
        self.assertEqual(self.request('articles')['total'], 1)
        with self.assertRaises(Exception):self.request('semantic/settings', {'enabled':True}, {'Origin':'https://other.example'})
        self.assertFalse(self.request('semantic/status')['config']['enabled'])


if __name__ == '__main__':unittest.main()
