# core/skill_loader.py
import os
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

SKILL_TRIGGERS = {
    'nodejs.md': [
        'node', 'nodejs', 'npm', 'express', '.js', 'javascript',
        'package.json', 'require(', 'import ', 'module.exports',
        'async/await', 'middleware', 'route', 'server.js', 'index.js',
        'next.js', 'nestjs', 'fastify', 'koa', 'eaddrinuse', 'esm',
    ],
    'python.md': [
        'python', 'flask', 'fastapi', 'django', 'pip', '.py',
        'requirements.txt', 'def ', 'class ', 'import ', 'virtualenv',
        'venv', 'pylint', 'pytest', 'sqlalchemy', 'pydantic',
        'blueprint', 'wsgi', 'asgi', 'uvicorn', 'gunicorn',
    ],
    'sql.md': [
        'sql', 'postgresql', 'postgres', 'sqlite', 'mysql', 'neon',
        'database', 'db', 'table', 'query', 'select', 'insert',
        'update', 'delete', 'migration', 'schema', 'join', 'index',
        'transaction', 'knex', 'sqlalchemy', 'orm', 'sequelize',
        'truncate', 'drop', 'constraint', 'foreign key',
    ],
    'debug.md': [
        'erreur', 'error', 'bug', 'traceback', 'exception', 'crash',
        'undefined', 'null', 'none', 'failed', 'ne fonctionne pas',
        'problème', 'problem', 'issue', 'stack trace', 'stderr',
        'typeerror', 'attributeerror', 'keyerror', 'syntaxerror',
        'cannot read', 'is not a function', 'module not found',
        'connection refused', 'timeout', '500', '404', 'cors',
    ],
    'api.md': [
        'api', 'rest', 'endpoint', 'fetch', 'axios', 'requests',
        'http', 'https', 'webhook', 'openrouter', 'anthropic',
        'openai', 'bearer', 'authorization', 'header', 'json',
        'post', 'get ', 'put ', 'delete', 'response', 'status code',
        'rate limit', '429', 'streaming', 'sse',
    ],
    'termux.md': [
        'termux', 'proot', 'debian', 'bash', 'shell', 'terminal',
        'linux', 'chmod', 'apt', 'pkg install', 'permission denied',
        'command not found', 'path', 'env', '.bashrc', 'cron',
        'script', 'systemd', 'service', 'daemon', 'arm',
        '--break-system-packages',
    ],
    'git.md': [
        'git', 'github', 'commit', 'push', 'pull', 'branch',
        'merge', 'clone', 'repository', 'repo', 'github actions',
        'ci/cd', 'workflow', 'deploy', 'render', 'heroku',
        '.gitignore', 'pull request', 'pr', 'conflict', 'rebase',
    ],
}


class SkillLoader:
    def __init__(self, skills_dir: str = None):
        if skills_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            skills_dir = os.path.join(base, 'skills')
        self.skills_dir = skills_dir
        self._cache: dict = {}

    def _load_skill(self, filename: str) -> str:
        if filename in self._cache:
            return self._cache[filename]
        path = os.path.join(self.skills_dir, filename)
        if not os.path.exists(path):
            logger.warning(f"Skill non trouvee: {path}")
            return ''
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self._cache[filename] = content
            return content
        except Exception as e:
            logger.error(f"Erreur lecture skill {filename}: {e}")
            return ''

    def detect_skills(self, message: str, history: list = None) -> List[Tuple[str, int]]:
        text = message.lower()
        if history:
            for msg in history[-4:]:
                c = msg.get('content', '')
                if isinstance(c, str):
                    text += ' ' + c.lower()
        scores = {}
        for skill_file, keywords in SKILL_TRIGGERS.items():
            score = sum(1 for kw in keywords if kw.lower() in text)
            if score > 0:
                scores[skill_file] = score
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    def get_context(self, message: str, history: list = None,
                    max_skills: int = 2, min_score: int = 2) -> str:
        detected = self.detect_skills(message, history)
        if not detected:
            return ''
        selected = [(fn, s) for fn, s in detected if s >= min_score][:max_skills]
        if not selected:
            return ''
        parts = []
        for skill_file, score in selected:
            content = self._load_skill(skill_file)
            if content:
                name = skill_file.replace('.md', '').upper()
                logger.info(f"Skill chargee: {skill_file} (score={score})")
                parts.append(f"[SKILL ACTIVE: {name}]\n{content}")
        return '\n\n---\n\n'.join(parts) if parts else ''

    def list_available(self) -> List[str]:
        if not os.path.exists(self.skills_dir):
            return []
        return [f for f in os.listdir(self.skills_dir) if f.endswith('.md')]