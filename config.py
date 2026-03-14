import os
import logging

logger = logging.getLogger(__name__)

class Config:
    # OpenRouter
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
    DEFAULT_MODEL = 'qwen/qwen3-coder:free'
    FREE_FALLBACKS = [
        'openrouter/hunter-alpha',
        'qwen/qwen3-coder:free',
        'qwen/qwen3-next-80b-a3b-instruct:free',
        'openai/gpt-oss-120b:free',
        'stepfun/step-3.5-flash:free',
        'nvidia/nemotron-3-nano-30b-a3b:free',
        'meta-llama/llama-3.3-70b-instruct:free',
        'arcee-ai/trinity-large-preview:free',
        'z-ai/glm-4.5-air:free',
        'mistralai/mistral-small-3.1-24b-instruct:free',
        'openrouter/free',
    ]
    MODEL_TIMEOUTS = {
        'qwen/qwen3-coder:free'                        : 120,
        'openrouter/hunter-alpha'                      : 120,
        'qwen/qwen3-next-80b-a3b-instruct:free'        : 100,
        'openai/gpt-oss-120b:free'                     : 100,
        'stepfun/step-3.5-flash:free'                  :  90,
        'nvidia/nemotron-3-nano-30b-a3b:free'          :  60,
        'meta-llama/llama-3.3-70b-instruct:free'       :  70,
        'arcee-ai/trinity-large-preview:free'          :  50,
        'z-ai/glm-4.5-air:free'                        :  60,
        'mistralai/mistral-small-3.1-24b-instruct:free':  45,
        'openrouter/free'                              :  90,
    }
    DEFAULT_TIMEOUT = 90

    # Sécurité
    APP_PASSWORD = os.environ.get('APP_PASSWORD', 'devagent')

    # BUG-02 FIX : os.urandom() régénère une clé différente à chaque restart →
    # toutes les sessions Flask sont invalidées. On utilise une valeur fixe de
    # fallback (dev uniquement). En production, SECRET_KEY DOIT être dans l'env.
    _secret = os.environ.get('SECRET_KEY', '')
    if not _secret:
        _secret = 'alt3267819hozvy-0036818hzizboboed'
        logger.warning(
            '[CONFIG] SECRET_KEY non définie dans l\'environnement. '
            'Utilisation de la clé de dev — NE PAS utiliser en production !'
        )
    SECRET_KEY = _secret

    # Agent
    MAX_STEPS = int(os.environ.get('MAX_STEPS', '15'))
    MAX_HISTORY_TOKENS = 8000
    CONTEXT_WINDOW = 20

    # Base de données
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///devagent.db')

    # Workspace
    WORKSPACE_ROOT = os.environ.get('WORKSPACE_ROOT', './workspaces')

    # Upload
    UPLOAD_MAX_SIZE = 500_000  # 500 KB
    ALLOWED_UPLOAD_EXT = {
        '.py', '.js', '.ts', '.json', '.txt', '.md',
        '.csv', '.html', '.css', '.sh', '.yaml', '.yml',
        '.sql', '.env', '.toml', '.xml',
    }

    # Cache
    # BUG-20 FIX (partiel) : le chemin absolu final est calculé dans ToolCache
    # pour éviter la dépendance au CWD au moment de l'import.
    CACHE_DB_PATH = os.environ.get('CACHE_DB_PATH', 'tool_cache.db')
    CACHE_DEFAULT_TTL = 300  # secondes
