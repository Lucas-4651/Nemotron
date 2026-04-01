# core/tool_cache.py — v4.0
# BUG-FIX #8  : race condition L1 — ajout de RLock autour de toutes les ops sur self._l1
# NEW : WAL mode SQLite (lectures concurrentes sans verrou)
# NEW : L1 cache mémoire thread-safe (dict + RLock)
# NEW : TTL personnalisable par tool_name
# NEW : purge auto des entrées expirées
import sqlite3
import json
import time
import os
import hashlib
import threading
from typing import Optional, Dict
from config import Config


# TTL spécifiques par outil (en secondes)
TOOL_TTLS: Dict[str, int] = {
    'read_file'       : 60,
    'view_file'       : 60,
    'list_directory'  : 30,
    'get_file_info'   : 30,
    'grep_files'      : 120,
    'semantic_search' : 300,
    'web_search'      : 600,
    'fetch_url'       : 300,
    'get_dependencies': 120,
    'project_map'     : 60,
    'find_files'      : 30,
}

# Outils jamais mis en cache (effets de bord)
NO_CACHE = {
    'write_file', 'append_file', 'delete_path', 'move_file',
    'execute_command', 'run_python', 'run_node', 'run_linter',
    'run_tests', 'build_project', 'save_memory', 'str_replace',
    'multi_str_replace', 'insert_lines', 'create_directory',
}


class ToolCache:
    def __init__(self, db_path: str = None, workspace_path: str = ''):
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            raw      = Config.CACHE_DB_PATH
            db_path  = raw if os.path.isabs(raw) else os.path.join(project_root, raw)

        self.db_path    = db_path
        self._db_lock   = threading.Lock()        # lock pour les opérations SQLite
        # BUG-FIX #8 : RLock réentrant pour protéger le dict L1 en multi-thread
        self._l1_lock   = threading.RLock()
        self._l1: Dict[str, tuple] = {}           # {key: (result, expires)}
        self._l1_max    = 200

        self._ws_prefix = hashlib.md5(
            os.path.abspath(workspace_path).encode()
        ).hexdigest()[:8] if workspace_path else ''

        self._init_db()
        self._last_purge = time.time()

    def _init_db(self):
        conn = self._conn()
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                key       TEXT PRIMARY KEY,
                result    TEXT,
                expires   REAL,
                tool_name TEXT
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_expires   ON cache(expires)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tool_name ON cache(tool_name)')
        conn.commit()
        conn.close()

    def _conn(self):
        return sqlite3.connect(self.db_path, timeout=5)

    def _key(self, name: str, args: dict) -> str:
        raw = self._ws_prefix + name + json.dumps(args, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, name: str, args: dict) -> Optional[str]:
        if name in NO_CACHE:
            return None
        key = self._key(name, args)
        now = time.time()

        # BUG-FIX #8 : lecture L1 sous lock
        with self._l1_lock:
            if key in self._l1:
                result, expires = self._l1[key]
                if now < expires:
                    return result
                del self._l1[key]

        # L2 (SQLite)
        try:
            with self._db_lock:
                conn = self._conn()
                row  = conn.execute(
                    'SELECT result, expires FROM cache WHERE key = ?', (key,)
                ).fetchone()
                conn.close()
        except Exception:
            return None

        if not row:
            return None
        result, expires = row
        if now > expires:
            self._delete_key_async(key)
            return None

        # Remonter en L1
        self._l1_set(key, result, expires)
        return result

    def set(self, name: str, args: dict, result: str, ttl: int = None):
        if name in NO_CACHE:
            return
        ttl     = ttl or TOOL_TTLS.get(name, Config.CACHE_DEFAULT_TTL)
        key     = self._key(name, args)
        expires = time.time() + ttl

        self._l1_set(key, result, expires)

        try:
            with self._db_lock:
                conn = self._conn()
                conn.execute(
                    'REPLACE INTO cache (key, result, expires, tool_name) VALUES (?,?,?,?)',
                    (key, result, expires, name)
                )
                conn.commit()
                conn.close()
        except Exception as e:
            logger.warning(f'ToolCache.set error: {e}') if False else None

        if time.time() - self._last_purge > 300:
            self._purge_async()

    def _l1_set(self, key: str, result: str, expires: float):
        """BUG-FIX #8 : toujours sous RLock."""
        with self._l1_lock:
            if len(self._l1) >= self._l1_max:
                # Éviction FIFO simple
                try:
                    oldest = next(iter(self._l1))
                    del self._l1[oldest]
                except StopIteration:
                    pass
            self._l1[key] = (result, expires)

    def _delete_key_async(self, key: str):
        def _del():
            try:
                with self._db_lock:
                    conn = self._conn()
                    conn.execute('DELETE FROM cache WHERE key = ?', (key,))
                    conn.commit()
                    conn.close()
            except Exception:
                pass
        threading.Thread(target=_del, daemon=True).start()

    def _purge_async(self):
        self._last_purge = time.time()
        def _purge():
            try:
                with self._db_lock:
                    conn = self._conn()
                    conn.execute('DELETE FROM cache WHERE expires < ?', (time.time(),))
                    conn.commit()
                    conn.close()
            except Exception:
                pass
        threading.Thread(target=_purge, daemon=True).start()

    def invalidate_workspace(self):
        """Invalide tout le cache de ce workspace."""
        with self._l1_lock:
            self._l1.clear()
        try:
            with self._db_lock:
                conn = self._conn()
                conn.execute('DELETE FROM cache')
                conn.commit()
                conn.close()
        except Exception:
            pass

    def invalidate(self, tool_name: str = None):
        """BUG-FIX #8 : clear L1 sous lock."""
        with self._l1_lock:
            self._l1.clear()
        try:
            with self._db_lock:
                conn = self._conn()
                if tool_name is None:
                    conn.execute('DELETE FROM cache')
                else:
                    conn.execute('DELETE FROM cache WHERE tool_name = ?', (tool_name,))
                conn.commit()
                conn.close()
        except Exception:
            pass

    def stats(self) -> dict:
        try:
            with self._db_lock:
                conn  = self._conn()
                total = conn.execute('SELECT COUNT(*) FROM cache').fetchone()[0]
                valid = conn.execute(
                    'SELECT COUNT(*) FROM cache WHERE expires > ?', (time.time(),)
                ).fetchone()[0]
                conn.close()
            with self._l1_lock:
                l1_size = len(self._l1)
            return {'entries': total, 'valid': valid, 'l1': l1_size}
        except Exception:
            return {'entries': 0, 'valid': 0, 'l1': 0}
