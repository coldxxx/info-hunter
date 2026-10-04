"""Remove sources from the library while preserving their archived evidence."""
import datetime as dt


def schema(c):
    if 'deleted_at' not in {row[1] for row in c.execute('PRAGMA table_info(sources)')}:
        c.execute('ALTER TABLE sources ADD COLUMN deleted_at TEXT')


def delete(c, source_id):
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError('请选择要删除的来源')
    row = c.execute('SELECT deleted_at FROM sources WHERE id=?', (source_id,)).fetchone()
    if not row:
        raise ValueError('来源不存在')
    if row[0]:
        return {'ok': True, 'source_id': source_id, 'already_deleted': True, 'removed_topics': 0}
    removed = c.execute('SELECT count(*) FROM watch_sources WHERE source_id=?', (source_id,)).fetchone()[0]
    c.execute('UPDATE sources SET deleted_at=? WHERE id=?',
              (dt.datetime.now(dt.timezone.utc).isoformat(), source_id))
    for table in ('watch_sources', 'source_connections', 'source_controls', 'source_signals', 'submitted_links'):
        c.execute(f'DELETE FROM {table} WHERE source_id=?', (source_id,))
    # Keep articles, sightings, topic archives, media, translations and annotations.
    # The retained registry row keeps provenance and stops bundled sources respawning.
    return {'ok': True, 'source_id': source_id, 'removed_topics': removed}
