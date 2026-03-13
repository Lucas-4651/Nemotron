# core/agent.py
import json
import logging
from typing import List, Dict, Generator
from datetime import datetime

from core.llm_client import LLMClient
from core.tool_cache import ToolCache
from core.metrics import SessionMetrics
from core.summarizer import Summarizer
from core.skill_loader import SkillLoader
from tools import ToolManager
from config import Config

logger = logging.getLogger(__name__)

BASE_SYSTEM = """\
Tu es un agent IA expert en developpement logiciel, cree par Lucas46 Tech Studio.
Tu es specialise dans l'environnement Termux / Proot Debian (sans root).
Tu maitrises Python, JavaScript/Node.js, Bash, SQL, REST APIs, Express, Flask, \
PostgreSQL (Neon), SQLite, deploiement sur Render, GitHub Actions, et Android/WebView.

## Identite et valeurs
- Tu es direct, precis, pedagogue.
- Tu signales les bugs que tu remarques meme si on ne t'a pas demande.
- Tu preferes les solutions simples.
- Tu es honnete : si tu n'es pas sur, tu le dis et tu verifies avec les outils.

## Comportement avec les outils
- Toujours lire avant de modifier : view_file ou read_file avant tout changement.
- Modifications precises : prefere str_replace a write_file pour du code existant.
- Valider avant de livrer : run_python ou run_node pour tester.
- Chercher avant d'inventer : web_search ou fetch_url pour la doc et les erreurs.
- Enchaine les outils : explore -> lis -> modifie -> teste -> confirme.

## Format
- Francais par defaut.
- Concis dans le texte, complet dans le code.
- Explique les choix importants.

## Securite
- Jamais de commandes destructives sans confirmation.
- Jamais logger des cles API ou mots de passe.

## Skills
Quand [SKILL ACTIVE: ...] est present, suis ces instructions en priorite."""


class DevAgent:
    def __init__(self, workspace_path: str, config: dict = None):
        self.config = config or {}
        self.workspace_path = workspace_path
        self.api_key = self.config.get('api_key') or Config.OPENROUTER_API_KEY
        self.model = self.config.get('model', Config.DEFAULT_MODEL)
        self.fallbacks = self.config.get('fallback_models', Config.FREE_FALLBACKS)
        self.max_steps = self.config.get('max_steps', Config.MAX_STEPS)
        self.max_htoks = self.config.get('max_history_tokens', Config.MAX_HISTORY_TOKENS)
        self.ctx_win = self.config.get('context_window', Config.CONTEXT_WINDOW)

        self.llm = LLMClient(self.api_key, self.model, self.fallbacks)
        self.cache = ToolCache()
        self.metrics = SessionMetrics()
        self.summarizer = Summarizer(self.llm)
        self.skill_loader = SkillLoader()

        self.tool_mgr = ToolManager(workspace_path, self.config.get('allowed_commands'))
        self.tools_fn = self.tool_mgr.get_all_tools()
        self.tools_spec = self.tool_mgr.get_openrouter_tools_spec()

        self.history: List[Dict] = []
        self.reasoning_enabled = False
        self.memory_context = ''

    def _build_system(self, user_message: str = '') -> str:
        parts = [BASE_SYSTEM]
        if self.memory_context:
            parts.append(f'[MEMOIRE PERSISTANTE]\n{self.memory_context}')
        if user_message:
            skill_context = self.skill_loader.get_context(
                user_message, history=self.history, max_skills=2, min_score=2)
            if skill_context:
                parts.append(skill_context)
        return '\n\n---\n\n'.join(parts)

    def _est_tokens(self, text: str) -> int:
        return int(len(str(text).split()) * 1.3)

    def _hist_tokens(self) -> int:
        return sum(self._est_tokens(m.get('content') or '') for m in self.history)

    def _build_messages(self, system: str) -> List[dict]:
        msgs = [{'role': 'system', 'content': system}]
        if self._hist_tokens() > self.max_htoks:
            summary = self.summarizer.summarize_if_needed(self.history)
            if summary:
                msgs.append({'role': 'system', 'content': f'[RESUME]\n{summary}'})
            msgs.extend(self.history[-self.ctx_win:])
        else:
            msgs.extend(self.history[-self.ctx_win:])
        return msgs

    def stream_task(self, user_input: str) -> Generator[dict, None, None]:
        self.history.append({'role': 'user', 'content': user_input})
        system = self._build_system(user_input)

        detected = self.skill_loader.detect_skills(user_input, self.history[:-1])
        active = [fn.replace('.md', '') for fn, s in detected if s >= 2][:2]
        if active:
            yield {'type': 'skill', 'skills': active}

        for step in range(1, self.max_steps + 1):
            messages = self._build_messages(system)
            yield {'type': 'thinking', 'step': step, 'max': self.max_steps}

            tool_calls = None
            final_text = ""
            model_used = self.model

            for ev in self.llm.stream_call(messages, self.tools_spec, self.reasoning_enabled):
                if ev['type'] == 'token':
                    final_text += ev['text']
                    yield {'type': 'token', 'text': ev['text']}
                elif ev['type'] == 'tool_calls':
                    tool_calls = ev['calls']
                    model_used = ev['model']
                    self.metrics.add_req(ev.get('usage', {}))
                    break
                elif ev['type'] == 'done':
                    final_text = ev['text']
                    model_used = ev['model']
                    self.metrics.add_req(ev.get('usage', {}))
                    break
                elif ev['type'] == 'error':
                    self.history.append({'role': 'assistant', 'content': ev['text']})
                    yield {'type': 'error', 'text': ev['text']}
                    return

            if tool_calls:
                self.history.append({
                    'role': 'assistant', 'content': None, 'tool_calls': tool_calls})
                for tc in tool_calls:
                    tname = tc['function']['name']
                    try:
                        targs = json.loads(tc['function']['arguments'])
                    except:
                        targs = {}
                    cached_result = self.cache.get(tname, targs)
                    if cached_result is not None:
                        result = cached_result
                        cached = True
                    else:
                        yield {'type': 'tool_call', 'name': tname, 'args': targs}
                        try:
                            fn = self.tools_fn.get(tname)
                            result = str(fn(targs)) if fn else f"Outil inconnu: {tname}"
                        except Exception as e:
                            result = f"Erreur outil: {e}"
                        self.cache.set(tname, targs, result)
                        cached = False
                    self.metrics.add_tool(tname, cached)
                    yield {'type': 'tool_result', 'name': tname,
                           'result': result[:2000], 'cached': cached}
                    self.history.append({
                        'role': 'tool', 'tool_call_id': tc['id'],
                        'name': tname, 'content': result})
                continue

            self.history.append({'role': 'assistant', 'content': final_text})
            yield {'type': 'done', 'model': model_used, 'metrics': self.metrics.to_dict()}
            return

        yield {'type': 'error', 'text': f"Limite de {self.max_steps} etapes atteinte."}