# workspace/indexer.py — v3
# NEW : index persisté sur disque SQLite (pas de recalcul au restart)
# NEW : indexation incrémentale (seulement les fichiers modifiés)
# IMPROVED : snippet extraction plus intelligente
import os
import math
import re
import sqlite3
import json
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Optional


class CodeIndexer:
    EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.md', '.txt',
        '.html', '.css', '.sh', '.yaml', '.yml', '.sql', '.toml',
        '.env', '.xml', '.go', '.rs', '.java', '.c', '.cpp', '.h',
    }
    IGNORE_DIRS = {
        '__pycache__', '.git', 'node_modules', '.venv', 'venv',
        'dist', 'build', '.next', '.nuxt', 'coverage', '.tox',
    }
    MAX_FILE_SIZE = 150_000   # 150 KB
    MAX_FILES     = 800

    def __init__(self, workspace_path):
        self.workspace  = Path(workspace_path).resolve()
        self._db_path   = str(self.workspace / '.nemotron_index.db')
        self._idf: Dict[str, float] = {}
        self._init_db()
        self._load_idf()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS files (
                path     TEXT PRIMARY KEY,
                content  TEXT,
                tfidf    TEXT,   -- JSON
                mtime    REAL,
                hash     TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def _conn(self):
        return sqlite3.connect(self._db_path, timeout=5)

    def _load_idf(self):
        try:
            conn = self._conn()
            row  = conn.execute("SELECT value FROM meta WHERE key='idf'").fetchone()
            conn.close()
            if row:
                self._idf = json.loads(row[0])
        except Exception:
            pass

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'[a-z0-9_]{2,}', text.lower())

    def _tf(self, tokens: List[str]) -> Dict[str, float]:
        if not tokens: return {}
        freq: Dict[str, int] = {}
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1
        total = len(tokens)
        return {t: c / total for t, c in freq.items()}

    def _file_hash(self, path: Path) -> str:
        try:
            return hashlib.md5(path.read_bytes()).hexdigest()[:16]
        except Exception:
            return ''

    def index_directory(self) -> int:
        """
        Indexation incrémentale : ne re-indexe que les fichiers modifiés.
        Retourne le nombre total de fichiers indexés.
        """
        conn      = self._conn()
        docs      = []
        new_count = 0

        for root, dirs, files in os.walk(self.workspace):
            dirs[:] = [d for d in dirs
                       if d not in self.IGNORE_DIRS and not d.startswith('.')]
            for fname in files:
                if len(docs) >= self.MAX_FILES:
                    break
                ext = os.path.splitext(fname)[1].lower()
                if ext not in self.EXTENSIONS:
                    continue
                fpath = Path(root) / fname
                try:
                    mtime = fpath.stat().st_mtime
                    size  = fpath.stat().st_size
                    if size > self.MAX_FILE_SIZE:
                        continue
                    rel    = str(fpath.relative_to(self.workspace))
                    fhash  = self._file_hash(fpath)
                    # Vérifier si déjà indexé et non modifié
                    row = conn.execute(
                        'SELECT hash FROM files WHERE path=?', (rel,)
                    ).fetchone()
                    if row and row[0] == fhash:
                        # Fichier inchangé — charger depuis la BD
                        existing = conn.execute(
                            'SELECT content, tfidf FROM files WHERE path=?', (rel,)
                        ).fetchone()
                        if existing:
                            docs.append({
                                'path'   : rel,
                                'content': existing[0],
                                'tfidf'  : json.loads(existing[1] or '{}'),
                            })
                            continue
                    # Nouveau fichier ou modifié
                    content = fpath.read_text(encoding='utf-8', errors='replace')
                    tokens  = self._tokenize(content)
                    docs.append({'path': rel, 'content': content, 'tokens': tokens,
                                 'mtime': mtime, 'hash': fhash})
                    new_count += 1
                except Exception:
                    continue

        # Recalculer IDF seulement si de nouveaux fichiers
        if new_count > 0 or not self._idf:
            df: Dict[str, int] = {}
            N = len(docs)
            for doc in docs:
                for t in set(doc.get('tokens') or self._tokenize(doc.get('content', ''))):
                    df[t] = df.get(t, 0) + 1
            self._idf = {
                t: math.log((N + 1) / (cnt + 1)) + 1
                for t, cnt in df.items()
            }
            # Persister IDF
            conn.execute(
                "REPLACE INTO meta (key, value) VALUES ('idf', ?)",
                (json.dumps(self._idf),)
            )

        # Persister les nouveaux fichiers
        for doc in docs:
            if 'tokens' not in doc:
                continue  # déjà en BD
            tf    = self._tf(doc['tokens'])
            tfidf = {t: v * self._idf.get(t, 1.0) for t, v in tf.items()}
            # Sauvegarder seulement les 200 mots clés (économie espace)
            top_tfidf = dict(sorted(tfidf.items(), key=lambda x: x[1], reverse=True)[:200])
            conn.execute(
                'REPLACE INTO files (path, content, tfidf, mtime, hash) VALUES (?,?,?,?,?)',
                (doc['path'], doc['content'][:50000],  # max 50KB content
                 json.dumps(top_tfidf), doc.get('mtime', 0), doc.get('hash', ''))
            )
            # Mettre le tfidf en mémoire pour la recherche
            doc['tfidf'] = top_tfidf

        conn.commit()
        conn.close()
        return len(docs)

    def search(self, query: str, n_results: int = 5) -> List[Dict]:
        """Recherche sémantique depuis l'index persisté."""
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []
        try:
            conn  = self._conn()
            rows  = conn.execute('SELECT path, content, tfidf FROM files').fetchall()
            conn.close()
        except Exception:
            return []

        scores = []
        for path, content, tfidf_json in rows:
            try:
                tfidf = json.loads(tfidf_json or '{}')
            except Exception:
                continue
            score = sum(tfidf.get(t, 0.0) for t in q_tokens)
            if score > 0:
                scores.append((score, path, content))

        scores.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, path, content in scores[:n_results]:
            snippet = self._extract_snippet(content or '', q_tokens)
            results.append({'path': path, 'content': snippet, 'score': round(score, 4)})
        return results

    def _extract_snippet(self, content: str, tokens: List[str], window: int = 300) -> str:
        lower    = content.lower()
        best_pos = 0
        best_cnt = 0
        step     = max(1, window // 4)
        for i in range(0, max(1, len(content) - window), step):
            chunk = lower[i:i + window]
            cnt   = sum(1 for t in tokens if t in chunk)
            if cnt > best_cnt:
                best_cnt = cnt
                best_pos = i
        return content[best_pos:best_pos + window].strip()
