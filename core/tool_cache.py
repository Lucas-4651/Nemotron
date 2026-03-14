import sqlite3
import json
import time
import os
import hashlib
from typing import Optional
from config import Config


class ToolCache:
    def __init__(self, db_path: str = None, workspace_path: str = ''):
        # BUG-20 FIX : le chemin 'tool_cache.db' est relatif au CWD au moment
        # de l'instanciation. Si le CWD change, plusieurs fichiers de cache
        # se créent à des endroits différents. On utilise un chemin absolu
        # basé sur la racine du projet.
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            raw = Config.CACHE_DB_PATH
            db_path = raw if os.path.isabs(raw) else os.path.join(project_root, raw)

        self.db_path = db_path

        # BUG-09 FIX : la clé de cache n'incluait pas le workspace. Ainsi
        # read_file({'path': 'config.py'}) du workspace A retournait le
        # résultat caché du workspace B. On inclut un préfixe opaque (hash
        # du chemin absolu du workspace) dans chaque clé.
        self._ws_prefix = hashlib.md5(
            os.path.abspath(workspace_path).encode()
        ).hexdigest()[:8] if workspace_path else ''

        self._init_db()

        self.no_cache = {
            'write_file', 'append_file', 'delete_path',
            'execute_command', 'run_python', 'run_node',
        }

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    key       TEXT PRIMARY KEY,
                    result    TEXT,
                    expires   REAL,
                    tool_name TEXT
                )
            ''')
            conn.execute(
                'CREATE INDEX IF NOT EXISTS idx_tool_name ON cache(tool_name)'
            )

    def _key(self, name: str, args: dict) -> str:
        raw = self._ws_prefix + name + json.dumps(args, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, name: str, args: dict) -> Optional[str]:
        if name in self.no_cache:
            return None
        key = self._key(name, args)
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                'SELECT result, expires FROM cache WHERE key = ?', (key,)
            )
            row = cur.fetchone()
        if not row:
            return None
        result, expires = row
        if time.time() > expires:
            self.delete_key(key)
            return None
        return result

    def set(self, name: str, args: dict, result: str,
            ttl: int = Config.CACHE_DEFAULT_TTL):
        if name in self.no_cache:
            return
        key     = self._key(name, args)
        expires = time.time() + ttl
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'REPLACE INTO cache (key, result, expires, tool_name) '
                'VALUES (?, ?, ?, ?)',
                (key, result, expires, name),
            )

    def delete_key(self, key: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM cache WHERE key = ?', (key,))

    def invalidate(self, tool_name: str = None):
        with sqlite3.connect(self.db_path) as conn:
            if tool_name is None:
                conn.execute('DELETE FROM cache')
            else:
                conn.execute(
                    'DELETE FROM cache WHERE tool_name = ?', (tool_name,)
                )

    def stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute('SELECT COUNT(*) FROM cache').fetchone()[0]
            valid = conn.execute(
                'SELECT COUNT(*) FROM cache WHERE expires > ?',
                (time.time(),),
            ).fetchone()[0]
        return {'entries': total, 'valid': valid}
