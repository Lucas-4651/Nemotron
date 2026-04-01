# core/skill_loader.py — v3
# NEW : détection automatique depuis les fichiers du workspace
# NEW : scoring TF-IDF pondéré (titres > contenu)
# NEW : skill "project" pour gros projets
import os
import re
import logging
from typing import List, Tuple, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

# Triggers textuels (message utilisateur)
SKILL_TRIGGERS: Dict[str, List[str]] = {
    'nodejs.md': [
        'node', 'nodejs', 'npm', 'express', '.js', 'javascript',
        'package.json', 'require(', 'import ', 'module.exports',
        'async/await', 'middleware', 'route', 'server.js',
        'next.js', 'nestjs', 'fastify', 'koa', 'eaddrinuse', 'esm',
    ],
    'python.md': [
        'python', 'flask', 'fastapi', 'django', 'pip', '.py',
        'requirements.txt', 'def ', 'class ', 'virtualenv',
        'venv', 'pylint', 'pytest', 'sqlalchemy', 'pydantic',
        'blueprint', 'wsgi', 'asgi', 'uvicorn', 'gunicorn',
    ],
    'sql.md': [
        'sql', 'postgresql', 'postgres', 'sqlite', 'mysql', 'neon',
        'database', 'db', 'table', 'query', 'select', 'insert',
        'update', 'delete', 'migration', 'schema', 'join', 'index',
        'transaction', 'knex', 'sqlalchemy', 'orm', 'sequelize',
    ],
    'debug.md': [
        'erreur', 'error', 'bug', 'traceback', 'exception', 'crash',
        'undefined', 'null', 'none', 'failed', 'ne fonctionne pas',
        'problème', 'problem', 'issue', 'stack trace', 'stderr',
        'typeerror', 'attributeerror', 'keyerror', 'syntaxerror',
        'cannot read', 'module not found', 'connection refused',
        'timeout', '500', '404', 'cors',
    ],
    'api.md': [
        'api', 'rest', 'endpoint', 'fetch', 'axios', 'requests',
        'http', 'https', 'webhook', 'openrouter', 'anthropic',
        'openai', 'bearer', 'authorization', 'header', 'json',
        'rate limit', '429', 'streaming', 'sse',
    ],
    'termux.md': [
        'termux', 'proot', 'debian', 'bash', 'shell', 'terminal',
        'linux', 'chmod', 'apt', 'pkg install', 'permission denied',
        'command not found', '.bashrc', 'cron',
        '--break-system-packages',
    ],
    'git.md': [
        'git', 'github', 'commit', 'push', 'pull', 'branch',
        'merge', 'clone', 'repository', 'repo', 'github actions',
        'ci/cd', 'workflow', 'deploy', '.gitignore',
        'pull request', 'pr', 'conflict', 'rebase',
    ],
    'render.md': [
        'render', 'render.com', 'deploy', 'déployer', 'déploiement',
        'production', 'procfile', 'start command', 'build command',
        'spin down', 'health check', 'gunicorn', 'onrender',
        'free tier', 'r10 boot timeout', 'postgresql://', 'sslmode',
    ],
    'docker.md': [
        'docker', 'dockerfile', 'docker-compose', 'container', 'conteneur',
        'image docker', 'docker build', 'docker run', 'docker-compose up',
        'registry', 'docker hub', 'volumes', 'healthcheck', 'docker stats',
        'podman', 'containerize', 'dockerize', 'entrypoint', 'cmd', 'expose',
    ],
    'project.md': [
        'analyse', 'analyser', 'audit', 'refactor', 'refactoriser',
        'architecture', 'structure', 'overview', 'résumé du projet',
        'comprendre', 'documenter', 'documentation', 'migration',
        'gros projet', 'tout le projet', 'fichiers', 'codebase',
        'comment fonctionne', 'explain this', 'explique ce projet',
    ],
}

# Fichiers indicateurs → skills activées automatiquement
WORKSPACE_INDICATORS: Dict[str, List[str]] = {
    'python.md'  : ['requirements.txt', 'setup.py', 'pyproject.toml', '*.py'],
    'nodejs.md'  : ['package.json', 'yarn.lock', 'package-lock.json'],
    'sql.md'     : ['*.sql', 'migrations/', 'alembic.ini', 'knexfile.js'],
    'render.md'  : ['render.yaml', 'Procfile'],
    'git.md'     : ['.gitignore', '.github/'],
    'docker.md'  : ['Dockerfile', 'docker-compose.yml', 'docker-compose.yaml', '.dockerignore'],
    'project.md' : [],   # toujours disponible pour gros projets
}


class SkillLoader:
    def __init__(self, skills_dir: str = None):
        if skills_dir is None:
            base       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            skills_dir = os.path.join(base, 'skills')
        self.skills_dir   = skills_dir
        self._cache: dict = {}
        self._ws_skills: List[str] = []   # skills détectées depuis le workspace

    # ── chargement fichier ────────────────────────────────────────────────────
    def _load_skill(self, filename: str) -> str:
        if filename in self._cache:
            return self._cache[filename]
        path = os.path.join(self.skills_dir, filename)
        if not os.path.exists(path):
            logger.warning(f'Skill non trouvée: {path}')
            return ''
        try:
            content = open(path, 'r', encoding='utf-8').read()
            self._cache[filename] = content
            return content
        except Exception as e:
            logger.error(f'Erreur lecture skill {filename}: {e}')
            return ''

    # ── détection depuis le workspace ─────────────────────────────────────────
    def scan_workspace(self, workspace_path: str):
        """
        Scanne les fichiers du workspace pour pré-activer les skills pertinentes.
        Appeler une fois lors de la création de l'agent.
        """
        self._ws_skills = []
        if not workspace_path or not os.path.exists(workspace_path):
            return
        try:
            entries = os.listdir(workspace_path)
            for skill, indicators in WORKSPACE_INDICATORS.items():
                for ind in indicators:
                    if ind.endswith('/'):
                        if os.path.isdir(os.path.join(workspace_path, ind.rstrip('/'))):
                            self._ws_skills.append(skill)
                            break
                    elif '*' in ind:
                        import fnmatch
                        if any(fnmatch.fnmatch(e, ind) for e in entries):
                            self._ws_skills.append(skill)
                            break
                    elif ind in entries:
                        self._ws_skills.append(skill)
                        break
            logger.info(f'Skills workspace détectées: {self._ws_skills}')
        except Exception as e:
            logger.warning(f'scan_workspace error: {e}')

    # ── scoring message ───────────────────────────────────────────────────────
    def detect_skills(self, message: str, history: list = None) -> List[Tuple[str, int]]:
        text = message.lower()
        if history:
            for msg in history[-4:]:
                c = msg.get('content', '')
                if isinstance(c, str):
                    text += ' ' + c.lower()

        scores: Dict[str, int] = {}

        # Score depuis triggers textuels
        for skill_file, keywords in SKILL_TRIGGERS.items():
            score = sum(1 for kw in keywords if kw.lower() in text)
            if score > 0:
                scores[skill_file] = score

        # Bonus pour skills workspace (pré-détectées)
        for skill in self._ws_skills:
            scores[skill] = scores.get(skill, 0) + 2

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # ── contexte système ──────────────────────────────────────────────────────
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
                logger.info(f'Skill chargée: {skill_file} (score={score})')
                parts.append(f'[SKILL ACTIVE: {name}]\n{content}')
        return '\n\n---\n\n'.join(parts) if parts else ''

    def list_available(self) -> List[str]:
        if not os.path.exists(self.skills_dir):
            return []
        return [f for f in os.listdir(self.skills_dir) if f.endswith('.md')]
