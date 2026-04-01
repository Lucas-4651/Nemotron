import os
import logging

logger = logging.getLogger(__name__)


class Config:
    # ── OpenRouter ──────────────────────────────────────────────────────────
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
    # BUG-FIX #4 : 'nvidia/nemotron-3-nano-30b-a3b:free' était dupliqué
    # → Python gardait la dernière valeur → timeout 60s au lieu de 140s
    DEFAULT_MODEL = 'nvidia/nemotron-3-nano-30b-a3b:free'

    AVAILABLE_MODELS = {
        'nvidia/nemotron-3-nano-30b-a3b:free'          : 'Nemotron Nano 30B (défaut)',
        'nvidia/nemotron-3-super-120b-a12b:free'       : 'Nemotron Super 120B',
        'meta-llama/llama-3.3-70b-instruct:free'       : 'Llama 3.3 70B Instruct',
        'qwen/qwen3-coder:free'                        : 'Qwen3 Coder 480B',
        'qwen/qwen3-next-80b-a3b-instruct:free'        : 'Qwen3 80B Instruct',
        'openai/gpt-oss-120b:free'                     : 'GPT-OSS 120B',
        'stepfun/step-3.5-flash:free'                  : 'Step-3.5 Flash',
        'arcee-ai/trinity-large-preview:free'          : 'Trinity Large',
        'z-ai/glm-4.5-air:free'                        : 'GLM-4.5 Air',
        'mistralai/mistral-small-3.1-24b-instruct:free': 'Mistral Small 24B',
        'openrouter/free'                              : 'Auto Free (OR)',
    }
    FREE_FALLBACKS = list(AVAILABLE_MODELS.keys())

    # BUG-FIX #4 : suppression du doublon — chaque clé a maintenant UN timeout unique
    MODEL_TIMEOUTS = {
        'nvidia/nemotron-3-nano-30b-a3b:free'          : 140,   # DEFAULT_MODEL → 140s
        'nvidia/nemotron-3-super-120b-a12b:free'       : 120,
        'meta-llama/llama-3.3-70b-instruct:free'       :  70,
        'qwen/qwen3-coder:free'                        : 120,
        'qwen/qwen3-next-80b-a3b-instruct:free'        : 100,
        'openai/gpt-oss-120b:free'                     : 100,
        'stepfun/step-3.5-flash:free'                  :  90,
        'arcee-ai/trinity-large-preview:free'          :  50,
        'z-ai/glm-4.5-air:free'                        :  60,
        'mistralai/mistral-small-3.1-24b-instruct:free':  45,
        'openrouter/free'                              :  90,
    }
    DEFAULT_TIMEOUT = 90

    # ── Sécurité ─────────────────────────────────────────────────────────────
    APP_PASSWORD     = os.environ.get('APP_PASSWORD', 'devagent')
    SESSION_LIFETIME = int(os.environ.get('SESSION_LIFETIME', '86400'))  # 24h

    # BUG-FIX mineur : avertissement clair mais ne bloque pas le démarrage en dev.
    # En prod, toujours setter SECRET_KEY en variable d'environnement.
    _secret = os.environ.get('SECRET_KEY', '')
    if not _secret:
        _secret = 'nemotron-dev-insecure-key-change-in-prod'
        logger.warning(
            "[CONFIG] ⚠️  SECRET_KEY non définie — sessions vulnérables. "
            "Setter SECRET_KEY en variable d'environnement pour la production !"
        )
    SECRET_KEY = _secret

    # ── Agent ─────────────────────────────────────────────────────────────────
    MAX_STEPS          = int(os.environ.get('MAX_STEPS',    '15'))
    MAX_HISTORY_TOKENS = int(os.environ.get('MAX_HTOKS',  '8000'))
    CONTEXT_WINDOW     = int(os.environ.get('CTX_WIN',      '20'))
    TOOL_TIMEOUT       = int(os.environ.get('TOOL_TIMEOUT', '30'))
    MAX_TOOLS_PER_STEP = int(os.environ.get('MAX_TOOLS',     '4'))

    # Bounds UI pour la config agent
    AGENT_CONFIG_BOUNDS = {
        'max_steps'         : (3, 30),
        'tool_timeout'      : (10, 120),
        'max_tools_per_step': (1, 6),
        'max_history_tokens': (2000, 20000),
        'temperature'       : (0.0, 1.0),
        'max_tokens'        : (512, 8192),
    }

    # Paramètres LLM par défaut
    LLM_TEMPERATURE = float(os.environ.get('LLM_TEMPERATURE', '0.2'))
    LLM_MAX_TOKENS  = int(os.environ.get('LLM_MAX_TOKENS',   '4096'))

    # ── Base de données ───────────────────────────────────────────────────────
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///devagent.db')

    # ── Workspace ─────────────────────────────────────────────────────────────
    WORKSPACE_ROOT = os.environ.get('WORKSPACE_ROOT', './workspaces')

    # ── Upload ────────────────────────────────────────────────────────────────
    UPLOAD_MAX_SIZE = 500_000
    ZIP_MAX_SIZE    = 10_000_000
    ALLOWED_UPLOAD_EXT = {
        '.py', '.js', '.ts', '.json', '.txt', '.md',
        '.csv', '.html', '.css', '.sh', '.yaml', '.yml',
        '.sql', '.env', '.toml', '.xml',
    }

    # ── Cache ─────────────────────────────────────────────────────────────────
    CACHE_DB_PATH     = os.environ.get('CACHE_DB_PATH', 'tool_cache.db')
    CACHE_DEFAULT_TTL = 300

    # ── Logs ──────────────────────────────────────────────────────────────────
    LOG_DIR   = os.environ.get('LOG_DIR',   'logs')
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
