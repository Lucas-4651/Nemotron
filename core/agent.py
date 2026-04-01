# core/agent.py — v4.0
# BUG-FIX #2  : _run_tools_parallel — résultats None si thread crash → TypeError
# BUG-FIX #5  : detect_intent — substring match sans word boundary → faux positifs
# BUG-FIX #10 : tokens streamés + tool_calls → texte perdu dans l'historique
# UPGRADE     : BASE_SYSTEM réécrit sur le modèle de comportement Claude
import json
import logging
import re
import threading
from typing import List, Dict, Generator, Callable, Optional

from core.llm_client   import LLMClient
from core.tool_cache   import ToolCache
from core.metrics      import SessionMetrics
from core.summarizer   import Summarizer
from core.skill_loader import SkillLoader
from tools             import ToolManager
from config            import Config

logger = logging.getLogger(__name__)

# ── Prompt système — style Claude ─────────────────────────────────────────────
BASE_SYSTEM = """Tu es Nemotron, un assistant IA expert en développement logiciel créé par Lucas46 Tech Studio.

## Identité et valeurs fondamentales

Tu combines une expertise technique pointue avec des valeurs claires :
- **Honnêteté** : tu dis la vérité même quand ce n'est pas ce que l'utilisateur veut entendre. Tu n'inventes pas de réponses, tu admets l'incertitude.
- **Utilité réelle** : ton but est de résoudre concrètement le problème, pas de paraître utile. Tu vas droit au but.
- **Rigueur** : tu ne codes pas à l'aveugle. Tu lis, tu comprends, puis tu agis. Les bugs que tu introduis te perturbent autant qu'ils perturbent l'utilisateur.
- **Calibration** : tu exprimes ton niveau de confiance. "Je pense que...", "Je ne suis pas certain mais...", "À 90% c'est ça..." Pas de fausse assurance.
- **Respect** : tu traites l'utilisateur comme un développeur intelligent capable de comprendre les détails techniques.

## Personnalité

Direct, concis, professionnel mais détendu. Tu n'es pas un assistant corporate — tu parles comme un senior dev avec qui on peut déboguer à 23h. Pas de remplissage, pas de phrases inutiles comme "Bien sûr !", "Absolument !", "Excellente question !". Tu vas droit au fait.

Tu réponds **en français** par défaut sauf si l'utilisateur écrit dans une autre langue, auquel cas tu t'adaptes naturellement.

Tu peux être en désaccord avec l'utilisateur quand il a tort — poliment mais fermement. Si son approche est sous-optimale, tu le dis et tu proposes mieux.

## Règle fondamentale — QUAND utiliser les outils

### N'utilise JAMAIS les outils pour :
- Salutations et bavardage ("ça va ?", "bonjour", "merci", "nickel")
- Questions générales sur la programmation que tu connais déjà
- Explications de concepts ("c'est quoi un JWT", "explique async/await")
- Comparaisons théoriques sans besoin de données live
- Questions sur toi-même

### Utilise les outils UNIQUEMENT quand :
- L'utilisateur demande d'agir sur des fichiers réels (modifier, créer, corriger)
- L'utilisateur demande d'exécuter du code
- Tu dois LIRE un fichier précis avant de répondre correctement
- Une recherche web est explicitement demandée ("cherche...", "trouve...")

## Règles d'action (quand tu utilises les outils)

1. `project_map()` ou `list_directory()` EN PREMIER sur tout projet inconnu
2. `view_file()` AVANT tout `str_replace` ou `write_file` — ne jamais modifier à l'aveugle
3. Préférer `str_replace` à `write_file` (modifications chirurgicales, pas d'écrasement)
4. Utiliser `multi_str_replace` pour plusieurs remplacements simultanés
5. `run_python` ou `run_node` pour valider après chaque modification importante
6. `grep_files` pour localiser avant de modifier
7. `save_memory` pour les infos importantes sur le projet/utilisateur

## Format des réponses

- Réponses courtes pour les questions courtes. Pas besoin de rédiger un roman pour "c'est quoi une regex ?".
- Pour le code : toujours expliquer CE QUE TU FAIS et POURQUOI, pas seulement comment.
- Si une tâche est ambiguë, tu poses UNE question précise plutôt que de supposer.
- Si tu n'as pas assez d'informations pour répondre correctement, tu le dis.

## Outils disponibles
Navigation : project_map, view_file, list_directory, find_files, get_file_info
Édition     : str_replace, multi_str_replace, insert_lines, write_file, append_file
Fichiers    : move_file, create_directory, delete_path, read_file
Code        : run_python, run_node, run_linter, run_tests, build_project, get_dependencies
Recherche   : grep_files, semantic_search, web_search, fetch_url
Shell       : execute_command
Mémoire     : save_memory
"""

# ── Détection d'intention ─────────────────────────────────────────────────────

# BUG-FIX #5 : utiliser des ensembles de mots complets (avec espaces ou début/fin)
# pour éviter les faux positifs substring ('import' dans 'important', etc.)
# Tous les tokens sont normalisés avec des espaces autour pour le matching.

ACTION_SIGNALS = {
    # Verbes d'action directs
    'crée', 'créer', 'create', 'génère', 'générer', 'generate',
    'modifie', 'modifier', 'modify', 'edit', 'change', 'changer',
    'corrige', 'corriger', 'fix', 'répare', 'réparer', 'repair',
    'installe', 'installer', 'install',
    'lance', 'lancer', 'run', 'exécute', 'exécuter', 'execute',
    'teste', 'tester', 'test',
    'build', 'compile',
    'déploie', 'déployer', 'deploy',
    'supprime', 'supprimer', 'delete', 'remove',
    'renomme', 'renommer', 'rename',
    'déplace', 'déplacer', 'move',
    'ajoute', 'ajouter', 'add',
    'refactor', 'refactorise',
    'optimise', 'optimiser', 'optimize',
    'migre', 'migrer', 'migrate',
    'cherche', 'recherche', 'search', 'trouve', 'trouver', 'find',
    'analyse', 'analyser', 'analyze', 'audit',
    'lit', 'lire', 'read',
    'montre', 'montrer', 'show', 'affiche', 'afficher', 'display',
    'liste', 'lister',
    'vérifie', 'vérifier', 'verify', 'check',
    # Extensions de fichiers (avec le point)
    '.py', '.js', '.ts', '.json', '.yaml', '.yml', '.sql',
    '.env', '.sh', '.html', '.css', '.md',
    # Termes fichier/projet (mots complets uniquement)
    'fichier', 'file', 'dossier', 'folder', 'répertoire', 'directory',
    'workspace', 'projet', 'project', 'script',
    'fonction', 'function', 'classe', 'method',
    'bug', 'erreur', 'error', 'exception', 'traceback',
    # Outils / frameworks
    'npm', 'pip', 'git', 'pytest', 'gunicorn', 'docker',
    'def ', 'class ', 'async ',
}

CHAT_SIGNALS = {
    'bonjour', 'salut', 'hello', 'hi', 'hey', 'coucou', 'bonsoir',
    'bro', 'mec', 'frérot', 'bzzoiro',
    'ca va', 'ça va', 'comment tu vas', 'how are you',
    'tu peux', 'tu sais', 'you can', 'can you',
    'merci', 'thank', 'thanks', 'parfait', 'nickel', 'cool', 'super',
    'excellent', 'bravo', 'bien joué', 'génial',
    'explique', 'explain', "c'est quoi", "qu'est-ce que", 'what is',
    'comment ça marche', 'how does', 'pourquoi', 'why',
    'différence entre', 'difference between',
    'avantage', 'advantage', 'inconvénient',
    'meilleur', 'best', 'recommande', 'recommend',
    'keskon', 'kek', 'wtf', 'lol', 'mdr',
    'tu es', 'vous êtes', 'who are you', 'what are you',
    'nemotron', 'agent',
    'ok', 'okay', 'oui', 'non', 'yes', 'no', "d'accord", 'compris',
    'je vois', 'je comprends', 'i see', 'understood',
}


def _tokenize(text: str) -> set:
    """Découpe un texte en tokens avec boundaries — évite les faux positifs substring."""
    # Extrait les mots et les extensions de fichier séparément
    words = set(re.findall(r'\b\w+\b', text.lower()))
    # Ajoute les extensions (avec le point) si présentes dans le texte brut
    exts  = set(re.findall(r'\.\w+', text.lower()))
    return words | exts


def detect_intent(message: str, history: List[Dict]) -> str:
    """
    Retourne 'chat' ou 'task'.

    BUG-FIX #5 : matching par token complet au lieu de substring.
    'import' ne matche plus 'important'. 'list' ne matche plus 'blacklist'.
    """
    text   = message.lower().strip()
    tokens = _tokenize(text)
    words  = text.split()

    # Toujours task si message long et non-conversationnel (> 20 mots)
    if len(words) > 20:
        if any(s in text for s in ('explique', 'explain', "c'est quoi", 'définit', 'compare')):
            if not any(s in text for s in ('.py', '.js', 'fichier', 'file', 'projet', 'workspace')):
                return 'chat'
        return 'task'

    # BUG-FIX #5 : matching token-based (intersection de sets) au lieu de substring
    chat_score = len(tokens & CHAT_SIGNALS)
    task_score = len(tokens & ACTION_SIGNALS)

    # Extensions de fichier dans le texte brut = toujours task
    if re.search(r'\.\w{2,4}\b', text):
        task_score += 1

    # Signal d'action explicite → toujours task
    if task_score >= 1:
        return 'task'

    # Signal conversationnel fort → chat
    if chat_score >= 1 and task_score == 0:
        return 'chat'

    # Message très court sans signal d'action → chat
    if len(words) <= 6 and task_score == 0:
        return 'chat'

    # Question rhétorique (se termine par ?)
    if text.endswith('?') and task_score == 0:
        if re.search(r'\.(py|js|ts|json|yaml|yml|sql|sh|html|css|md)\b', text):
            return 'task'
        if any(w in tokens for w in ('fichier', 'file', 'code', 'fonction', 'class')):
            return 'task'
        return 'chat'

    return 'task'


class DevAgent:

    def __init__(self, workspace_path: str, config: dict = None,
                 memory_save_cb: Optional[Callable] = None):
        self.config         = config or {}
        self.workspace_path = workspace_path
        self.api_key        = self.config.get('api_key') or Config.OPENROUTER_API_KEY
        self.model          = self.config.get('model', Config.DEFAULT_MODEL)
        self.fallbacks      = self.config.get('fallback_models', Config.FREE_FALLBACKS)

        self.max_steps          = self.config.get('max_steps',          Config.MAX_STEPS)
        self.max_htoks          = self.config.get('max_history_tokens', Config.MAX_HISTORY_TOKENS)
        self.ctx_win            = self.config.get('context_window',     Config.CONTEXT_WINDOW)
        self.max_tools_per_step = self.config.get('max_tools_per_step', Config.MAX_TOOLS_PER_STEP)
        self.tool_timeout       = self.config.get('tool_timeout',       Config.TOOL_TIMEOUT)

        self.llm          = LLMClient(self.api_key, self.model, self.fallbacks)
        self.cache        = ToolCache(workspace_path=workspace_path)
        self.metrics      = SessionMetrics()
        self.summarizer   = Summarizer(self.llm)
        self.skill_loader = SkillLoader()

        self.skill_loader.scan_workspace(workspace_path)

        self.tool_mgr   = ToolManager(
            workspace_path,
            self.config.get('allowed_commands'),
            memory_save_cb=memory_save_cb,
        )
        self.tools_fn   = self.tool_mgr.get_all_tools()
        self.tools_spec = self.tool_mgr.get_openrouter_tools_spec()

        self.history             : List[Dict] = []
        self.history_tokens      : int        = 0
        self.reasoning_enabled                = False
        self.memory_context                   = ''
        self._project_context                 = ''
        self._project_context_loaded          = False
        self._summary_cache                   = ''

    # ── Tokens ───────────────────────────────────────────────────────────────

    def _est_tokens(self, text: str) -> int:
        return max(1, len(str(text)) // 4)

    def _add_history(self, role: str, content, extra: dict = None):
        msg = {'role': role, 'content': content}
        if extra:
            msg.update(extra)
        self.history.append(msg)
        if content:
            self.history_tokens += self._est_tokens(str(content))

    # ── Contexte projet ───────────────────────────────────────────────────────

    def _load_project_context(self) -> str:
        parts = []
        try:
            pm_fn = self.tools_fn.get('project_map')
            if pm_fn:
                result = pm_fn({'max_depth': 3, 'show_sizes': False})
                if result and 'Erreur' not in str(result):
                    lines = result.split('\n')
                    if len(lines) > 60:
                        result = '\n'.join(lines[:60]) + f'\n  ... (+{len(lines)-60})'
                    parts.append(f'[STRUCTURE DU PROJET]\n{result}')
        except Exception as e:
            logger.warning(f'project_map error: {e}')
        try:
            rf_fn = self.tools_fn.get('read_file')
            if rf_fn:
                for readme in ['README.md', 'readme.md', 'README.txt']:
                    content = rf_fn({'path': readme})
                    if content and 'Erreur' not in str(content) and 'introuvable' not in str(content).lower():
                        snippet = content[:400] + ('...' if len(content) > 400 else '')
                        parts.append(f'[README]\n{snippet}')
                        break
        except Exception as e:
            logger.warning(f'readme load error: {e}')
        return '\n\n'.join(parts) if parts else ''

    # ── Historique sain ───────────────────────────────────────────────────────

    def _repair_history(self, history: List[Dict]) -> List[Dict]:
        repaired = []
        for msg in history:
            if msg.get('role') == 'tool':
                if not repaired or repaired[-1].get('role') != 'assistant':
                    continue
                if not repaired[-1].get('tool_calls'):
                    continue
            repaired.append(msg)
        return repaired

    def _smart_history(self) -> List[Dict]:
        full     = self._repair_history(self.history)
        budget   = self.max_htoks
        selected = []
        for msg in reversed(full):
            cost = self._est_tokens(str(msg.get('content', '') or ''))
            if budget - cost < 0 and selected:
                break
            budget -= cost
            selected.append(msg)
            if len(selected) >= self.ctx_win:
                break
        selected.reverse()
        while selected and selected[0].get('role') == 'tool':
            selected.pop(0)
        return selected

    # ── Système + messages ────────────────────────────────────────────────────

    def _build_system(self, user_message: str = '') -> str:
        parts = [BASE_SYSTEM]
        if self._project_context:
            parts.append(self._project_context)
        if self.memory_context:
            parts.append(f'[MÉMOIRE PERSISTANTE]\n{self.memory_context}')
        try:
            skill_ctx = self.skill_loader.get_context(
                user_message, history=self.history, max_skills=2, min_score=2
            )
            if skill_ctx:
                parts.append(skill_ctx)
        except Exception as e:
            logger.warning(f'Skill error: {e}')
        return '\n\n---\n\n'.join(parts)

    def _build_messages(self, system: str) -> List[Dict]:
        msgs = [{'role': 'system', 'content': system}]
        if self.history_tokens > self.max_htoks and self._summary_cache:
            msgs.append({'role': 'system', 'content': f'[RÉSUMÉ]\n{self._summary_cache}'})
        elif self.history_tokens > self.max_htoks:
            self._trigger_summary_async()
        msgs.extend(self._smart_history())
        return msgs

    def _trigger_summary_async(self):
        def _summarize():
            try:
                s = self.summarizer.summarize_if_needed(self.history)
                if s:
                    self._summary_cache = s
            except Exception as e:
                logger.warning(f'Summary async error: {e}')
        threading.Thread(target=_summarize, daemon=True).start()

    # ── Outils ───────────────────────────────────────────────────────────────

    def _run_tool(self, fn, args) -> str:
        if fn is None:
            return 'outil inconnu'
        result = [None]
        def target():
            try:
                result[0] = str(fn(args))
            except Exception as e:
                result[0] = f'Erreur outil: {e}'
        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(self.tool_timeout)
        if t.is_alive():
            return f'Timeout {self.tool_timeout}s'
        return result[0] or 'Aucun résultat'

    def _run_tools_parallel(self, tool_calls) -> List[tuple]:
        """
        BUG-FIX #2 : résultats initialisés avec un tuple d'erreur par défaut.
        Avant : results = [None] * n → crash TypeError sur unpacking si thread crash.
        Après : chaque slot a un tuple valide même en cas d'exception dans le thread.
        """
        results = [('unknown', 'Erreur: thread non terminé', False, '') for _ in tool_calls]

        def run_one(i, tc):
            name = tc['function'].get('name', 'unknown')
            try:
                args = json.loads(tc['function'].get('arguments', '{}') or '{}')
            except (json.JSONDecodeError, TypeError):
                args = {}
            try:
                if name in ('write_file', 'str_replace', 'multi_str_replace',
                            'insert_lines', 'append_file', 'delete_path', 'move_file'):
                    self.cache.invalidate(name)
                cached = self.cache.get(name, args)
                if cached is not None:
                    results[i] = (name, cached, True, tc.get('id', ''))
                    return
                fn = self.tools_fn.get(name)
                r  = self._run_tool(fn, args)
                self.cache.set(name, args, r)
                results[i] = (name, r, False, tc.get('id', ''))
            except Exception as e:
                results[i] = (name, f'Erreur inattendue: {e}', False, tc.get('id', ''))

        threads = []
        for i, tc in enumerate(tool_calls):
            t = threading.Thread(target=run_one, args=(i, tc))
            t.start()
            threads.append(t)
        for t in threads:
            t.join(self.tool_timeout + 5)  # timeout légèrement supérieur au tool_timeout interne
        return results

    # ── Stream principal ──────────────────────────────────────────────────────

    def stream_task(self, user_input: str) -> Generator[dict, None, None]:
        self._add_history('user', user_input)

        # ── DÉTECTION D'INTENTION ─────────────────────────────────────────────
        intent = detect_intent(user_input, self.history[:-1])
        logger.debug(f'Intent: {intent} for: {user_input[:60]}')

        # Charger le contexte projet seulement si c'est une TÂCHE
        if intent == 'task' and not self._project_context_loaded:
            self._project_context_loaded = True
            ctx = self._load_project_context()
            if ctx:
                self._project_context = ctx
        elif not self._project_context_loaded:
            self._project_context_loaded = True

        system = self._build_system(user_input)

        # Émettre les skills actives (seulement pour les tâches)
        if intent == 'task':
            try:
                detected = self.skill_loader.detect_skills(user_input, self.history[:-1])
                active   = [fn.replace('.md', '') for fn, s in detected if s >= 2][:3]
                if active:
                    yield {'type': 'skill', 'skills': active}
            except Exception as e:
                logger.warning(f'detect skills error: {e}')

        base_tool_choice = 'none' if intent == 'chat' else 'auto'
        tools_to_send    = None if intent == 'chat' else self.tools_spec

        # ── Boucle agent ──────────────────────────────────────────────────────
        for step in range(1, self.max_steps + 1):
            messages   = self._build_messages(system)
            tool_calls = None
            final_text = ''
            # BUG-FIX #10 : buffer pour capturer le texte streamé même si tool_calls suivent
            streamed_text = ''
            model_used = self.model

            yield {'type': 'thinking', 'step': step, 'max': self.max_steps}

            try:
                tc = 'none' if (step == self.max_steps or intent == 'chat') else base_tool_choice

                for ev in self.llm.stream_call(
                    messages, tools_to_send, self.reasoning_enabled, tool_choice=tc
                ):
                    if ev['type'] == 'reasoning_token':
                        yield {'type': 'reasoning_token', 'text': ev['text']}

                    elif ev['type'] == 'token':
                        streamed_text += ev['text']
                        final_text    += ev['text']
                        yield {'type': 'token', 'text': ev['text']}

                    elif ev['type'] == 'tool_calls':
                        tool_calls = ev['calls'][:self.max_tools_per_step]
                        model_used = ev.get('model', self.model)
                        self.metrics.add_req(ev.get('usage', {}))
                        break

                    elif ev['type'] == 'done':
                        final_text = ev.get('text', '') or streamed_text
                        model_used = ev.get('model', self.model)
                        self.metrics.add_req(ev.get('usage', {}))
                        break

                    elif ev['type'] == 'error':
                        # BUG-FIX #10 : stocker le texte streamé si disponible
                        if streamed_text:
                            self._add_history('assistant', streamed_text)
                        else:
                            self._add_history('assistant', ev.get('text', ''))
                        yield {'type': 'error', 'text': ev.get('text', 'Erreur LLM')}
                        return

            except Exception as e:
                yield {'type': 'error', 'text': f'LLM error: {e}'}
                return

            # ── Exécution des outils ──────────────────────────────────────────
            if tool_calls:
                # BUG-FIX #10 : si du texte a été streamé avant les tool_calls,
                # le stocker dans l'historique comme contenu textuel de l'assistant
                # puis l'assistant message avec tool_calls (content=None) séparément.
                if streamed_text:
                    self.history.append({
                        'role'   : 'assistant',
                        'content': streamed_text,
                    })

                self.history.append({
                    'role'      : 'assistant',
                    'content'   : None,
                    'tool_calls': tool_calls,
                })
                for tc_item in tool_calls:
                    name = tc_item['function'].get('name', 'unknown')
                    try:
                        args = json.loads(tc_item['function'].get('arguments', '{}') or '{}')
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    yield {'type': 'tool_call', 'name': name, 'args': args}

                results = self._run_tools_parallel(tool_calls)

                for name, result, cached, tc_id in results:
                    self.metrics.add_tool(name, cached)
                    yield {
                        'type'  : 'tool_result',
                        'name'  : name,
                        'result': result[:3000],
                        'cached': cached,
                    }
                    self.history.append({
                        'role'        : 'tool',
                        'tool_call_id': tc_id,
                        'name'        : name,
                        'content'     : result[:8000],
                    })
                continue

            # ── Fin ───────────────────────────────────────────────────────────
            self._add_history('assistant', final_text or streamed_text)
            yield {
                'type'   : 'done',
                'model'  : model_used,
                'metrics': self.metrics.to_dict(),
                'intent' : intent,
            }
            return

        yield {'type': 'error', 'text': f'max_steps ({self.max_steps}) atteint'}
