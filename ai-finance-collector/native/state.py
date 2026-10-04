"""Explicit native state preparation; importing this module creates no files."""
import os
import secrets
import sqlite3


def prepare(root):
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    token_path = root / 'token'
    if not token_path.exists():
        fd = os.open(token_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write(secrets.token_urlsafe(48))
    token = token_path.read_text().strip()
    return token_path, token


def open_database(root):
    c = sqlite3.connect(root / 'native.sqlite3', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c
