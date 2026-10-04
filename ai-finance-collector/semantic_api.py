"""Local-only HTTP operations for semantic deduplication."""
import semantic
import semantic_models


def get(path, q, c):
    if path == '/api/semantic/status':
        return semantic.status(c)
    if path == '/api/semantic/pairs':
        return semantic.pairs(c, q)
    if path == '/api/semantic/labels':
        return {'cases': semantic.export_labels(c)}
    return None


def post(path, body, c):
    if path == '/api/semantic/settings':
        return {'config': semantic.configure(c, body)}
    if path == '/api/semantic/run':
        topic = body.get('watch_id') or None
        if topic and not c.execute('SELECT 1 FROM watch_topics WHERE id=?', (topic,)).fetchone():
            raise ValueError('主题不存在')
        if body.get('retry'):
            c.execute("UPDATE semantic_jobs SET status='queued',attempts=0,next_at=0,error='' WHERE status='failed'")
        count = semantic.enqueue(c, topic, body.get('force') is True)
        return {'queued': count, 'enabled': semantic.settings(c)['enabled']}
    if path == '/api/semantic/health':
        return semantic_models.health(semantic.settings(c))
    if path == '/api/semantic/review':
        return semantic.review(c, body['pair_id'], body['relation'], body.get('note', ''), body.get('expected'))
    if path == '/api/semantic/split':
        return semantic.split(c, body['article_id'])
    if path == '/api/semantic/undo':
        return semantic.undo(c, body['event_id'])
    return None
