"""SQLite connections and additive initialization for the collector archive."""
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3

import content_store
import dedup
import interests
import reddit_quality
import semantic
import source_lifecycle
import translation
import watchlists


def connect(db):
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA secure_delete=ON')
    return c


def initialize(connect, root, ai_words):
    with connect() as c:
        # Dedup adds a grouping index; preserve all original records and annotations.
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='articles'").fetchone() and not c.execute("SELECT 1 FROM sqlite_master WHERE name='article_duplicates'").fetchone() and c.execute('SELECT count(*) FROM articles').fetchone()[0]:
            folder=Path(os.environ.get('RADAR_BACKUP_DIR',str(root/'backups')));folder.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(folder/('pre-cross-source-dedup-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')) as out:c.backup(out)
        # Snapshot before the developer relevance migration. Articles are never rewritten.
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='watch_topics'").fetchone() and not c.execute("SELECT 1 FROM sqlite_master WHERE name='article_focus'").fetchone():
            folder=Path(os.environ.get('RADAR_BACKUP_DIR',str(root/'backups')));folder.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(folder/('pre-developer-focus-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')) as out:c.backup(out)
        # Back up before the additive topic migration; preserve article contents.
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='articles'").fetchone() and not c.execute("SELECT 1 FROM sqlite_master WHERE name='watch_topics'").fetchone() and c.execute('SELECT count(*) FROM articles').fetchone()[0]:
            folder=Path(os.environ.get('RADAR_BACKUP_DIR',str(root/'backups')));folder.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(folder/('pre-topics-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')) as out:c.backup(out)
        # Snapshot an existing archive before the additive preference migration.
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='articles'").fetchone() and not c.execute("SELECT 1 FROM sqlite_master WHERE name='source_signals'").fetchone():
            if c.execute('SELECT count(*) FROM articles').fetchone()[0]:
                folder=Path(os.environ.get('RADAR_BACKUP_DIR',str(root/'backups')))
                folder.mkdir(parents=True,exist_ok=True)
                with sqlite3.connect(folder/('pre-preferences-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')) as out:c.backup(out)
        c.executescript('''
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, config TEXT NOT NULL, status TEXT DEFAULT '未采集', checked_at TEXT, success_at TEXT, error TEXT, last_count INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS articles(id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, title TEXT NOT NULL, excerpt TEXT, publisher TEXT, region TEXT, language TEXT, kind TEXT, topics TEXT, published_at TEXT, collected_at TEXT, source_id TEXT, starred INTEGER DEFAULT 0, note TEXT DEFAULT '', review TEXT DEFAULT '未核验');
        CREATE TABLE IF NOT EXISTS sightings(article_id TEXT, source_id TEXT, seen_at TEXT, PRIMARY KEY(article_id,source_id));
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, result TEXT);
        CREATE INDEX IF NOT EXISTS article_time ON articles(published_at);
        ''')
        content_store.schema(c)
        interests.schema(c)
        source_lifecycle.schema(c)
        translation.schema(c)
        for s in json.loads((root / 'sources.json').read_text()):
            c.execute('INSERT INTO sources(id,config) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config', (s['id'], json.dumps(s, ensure_ascii=False)))
        semantic.schema(c)
        watchlists.bootstrap(c,ai_words)
        reddit_quality.bootstrap(c)
        dedup.bootstrap(c)
        semantic.rebuild(c)
        c.execute("INSERT OR IGNORE INTO article_retention SELECT id,? FROM articles WHERE url LIKE 'https://%reddit.com/%'",(__import__("time").time()+48*3600,))
