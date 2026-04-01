# core/llm_client.py — v4.0
# BUG-FIX #3 : _parse_stream — fn.get('arguments') peut être None → TypeError crash stream
# BUG-FIX #6 : simple_call — resp.json() peut lever une exception sur HTML d'erreur
import requests
import json
import time
import logging
from typing import List, Optional, Generator, Dict, Any
from config import Config

logger = logging.getLogger(__name__)


# Profils de paramètres selon le contexte d'appel
LLM_PROFILES: Dict[str, Dict[str, Any]] = {
    # Agent principal — précision maximale, code fiable
    'agent': {
        'temperature'       : 0.2,
        'top_p'             : 0.9,
        'frequency_penalty' : 0.05,
        'presence_penalty'  : 0.0,
        'max_tokens'        : 4096,
    },
    # Résumé / one-shot court
    'summary': {
        'temperature'       : 0.3,
        'top_p'             : 0.9,
        'frequency_penalty' : 0.0,
        'presence_penalty'  : 0.0,
        'max_tokens'        : 512,
    },
    # Auto-nommage conversation (très court)
    'naming': {
        'temperature'       : 0.5,
        'top_p'             : 0.9,
        'frequency_penalty' : 0.3,
        'presence_penalty'  : 0.1,
        'max_tokens'        : 20,
    },
    # Raisonnement étendu activé
    'reasoning': {
        'temperature'       : 0.1,
        'top_p'             : 0.95,
        'frequency_penalty' : 0.0,
        'presence_penalty'  : 0.0,
        'max_tokens'        : 8192,
    },
}


class LLMClient:
    API_URL = 'https://openrouter.ai/api/v1/chat/completions'

    def __init__(self, api_key: str, model: str, fallbacks: List[str]):
        self.api_key   = api_key
        self.model     = model
        self.fallbacks = fallbacks
        self.timeouts  = Config.MODEL_TIMEOUTS
        # Session persistée → TCP keep-alive, DNS cache
        self._session  = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/json',
            'HTTP-Referer' : 'https://nemotron.lucas46.dev',
            'X-Title'      : 'Nemotron Dev Agent',
        })

    def _auth_headers(self) -> dict:
        return {'Authorization': f'Bearer {self.api_key}'}

    def _timeout_for(self, model: str) -> int:
        return self.timeouts.get(model, Config.DEFAULT_TIMEOUT)

    def _payload(self,
                 messages       : List[dict],
                 model          : str,
                 tools_spec     : Optional[List]  = None,
                 stream         : bool            = False,
                 reasoning      : bool            = False,
                 profile        : str             = 'agent',
                 tool_choice    : str             = 'auto',
                 max_tokens     : Optional[int]   = None,
                 response_format: Optional[dict]  = None,
                 extra_params   : Optional[dict]  = None,
                 ) -> dict:
        params = LLM_PROFILES.get(profile, LLM_PROFILES['agent']).copy()
        if reasoning:
            params = LLM_PROFILES['reasoning'].copy()

        p: dict = {
            'model'             : model,
            'messages'          : messages,
            'stream'            : stream,
            'temperature'       : params['temperature'],
            'top_p'             : params['top_p'],
            'frequency_penalty' : params['frequency_penalty'],
            'presence_penalty'  : params['presence_penalty'],
            'max_tokens'        : max_tokens or params['max_tokens'],
        }

        if reasoning:
            p['reasoning'] = {
                'effort'           : 'high',
                'include_reasoning': True,
            }

        if tools_spec:
            p['tools']       = tools_spec
            p['tool_choice'] = tool_choice

        if response_format:
            p['response_format'] = response_format

        if extra_params:
            p.update(extra_params)

        return p

    # ─── simple call ─────────────────────────────────────────────────────────

    def simple_call(self,
                    messages       : List[dict],
                    reasoning      : bool            = False,
                    profile        : str             = 'summary',
                    response_format: Optional[dict]  = None,
                    ) -> Optional[str]:
        """Appel non-streaming — résumé, nommage, one-shot."""
        if not self.api_key:
            return None
        for model in [self.model] + self.fallbacks:
            for attempt in range(3):
                try:
                    resp = self._session.post(
                        self.API_URL,
                        headers=self._auth_headers(),
                        json=self._payload(messages, model,
                                           stream=False,
                                           reasoning=reasoning,
                                           profile=profile,
                                           response_format=response_format),
                        timeout=self._timeout_for(model),
                    )
                    if resp.status_code == 401:
                        logger.error('simple_call: clé API invalide (401)')
                        return None
                    if resp.status_code == 429:
                        time.sleep(2 ** attempt)
                        continue
                    if resp.status_code >= 500:
                        logger.warning(f'simple_call {model}: server error {resp.status_code}')
                        break
                    resp.raise_for_status()

                    # BUG-FIX #6 : resp.json() peut lever ValueError/JSONDecodeError
                    # si le serveur retourne du HTML (erreur de proxy, maintenance)
                    try:
                        data = resp.json()
                    except (ValueError, json.JSONDecodeError) as e:
                        logger.warning(f'simple_call {model}: réponse non-JSON: {e} | body: {resp.text[:200]}')
                        break

                    choices = data.get('choices')
                    if not choices:
                        logger.warning(f'simple_call {model}: pas de choices dans la réponse')
                        break

                    text = choices[0].get('message', {}).get('content', '')
                    return text

                except requests.exceptions.Timeout:
                    logger.warning(f'simple_call {model}: timeout')
                    break
                except Exception as e:
                    logger.warning(f'simple_call {model} attempt {attempt}: {e}')
                    break
        return None

    # ─── stream call ─────────────────────────────────────────────────────────

    def stream_call(self,
                    messages    : List[dict],
                    tools_spec  : Optional[List],
                    reasoning   : bool = False,
                    tool_choice : str  = 'auto',
                    ) -> Generator[dict, None, None]:
        """
        Générateur SSE → tokens, tool_calls, reasoning_tokens, done, error.
        """
        if not self.api_key:
            yield {'type': 'error', 'text': 'Clé API manquante'}
            return

        queue = [self.model] + [m for m in self.fallbacks if m != self.model]

        for model in queue:
            timeout = self._timeout_for(model)
            payload = self._payload(
                messages, model,
                tools_spec  = tools_spec,
                stream      = True,
                reasoning   = reasoning,
                profile     = 'agent',
                tool_choice = tool_choice,
            )

            for attempt in range(2):
                try:
                    resp = self._session.post(
                        self.API_URL,
                        headers=self._auth_headers(),
                        json=payload,
                        stream=True,
                        timeout=(15, timeout),
                    )
                    if resp.status_code == 401:
                        yield {'type': 'error', 'text': 'Clé API invalide (401)'}
                        return
                    if resp.status_code == 429:
                        time.sleep(2 ** attempt)
                        continue
                    if resp.status_code >= 500:
                        logger.warning(f'stream_call {model}: server error {resp.status_code}')
                        break
                    resp.raise_for_status()
                    yield from self._parse_stream(resp, model)
                    return

                except requests.exceptions.Timeout:
                    logger.warning(f'stream_call {model}: timeout ({timeout}s)')
                    break
                except Exception as e:
                    logger.error(f'stream_call {model}: {e}')
                    break

        yield {'type': 'error', 'text': 'Tous les modèles ont échoué.'}

    # ─── parsing SSE ─────────────────────────────────────────────────────────

    def _parse_stream(self, resp, model: str) -> Generator[dict, None, None]:
        text_buf      = ''
        reasoning_buf = ''
        tc_buf        = []
        usage         = {}
        finish        = ''

        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode('utf-8') if isinstance(line, bytes) else line
            if line == 'data: [DONE]':
                break
            if line.startswith(': ') or not line.startswith('data: '):
                continue
            try:
                chunk = json.loads(line[6:])
            except (json.JSONDecodeError, ValueError):
                continue

            if chunk.get('usage'):
                usage = chunk['usage']

            choices = chunk.get('choices') or []
            if not choices:
                continue

            delta  = choices[0].get('delta') or {}
            reason = choices[0].get('finish_reason')
            if reason:
                finish = reason

            # ── Tokens de raisonnement ────────────────────────────────────
            r_tok = delta.get('reasoning') or ''
            if r_tok:
                reasoning_buf += r_tok
                yield {'type': 'reasoning_token', 'text': r_tok}

            # ── Tokens de réponse normale ─────────────────────────────────
            tok = delta.get('content') or ''
            if tok:
                text_buf += tok
                yield {'type': 'token', 'text': tok}

            # ── Tool calls (accumulation incrémentale) ────────────────────
            for tcd in delta.get('tool_calls') or []:
                idx = tcd.get('index', 0)
                while len(tc_buf) <= idx:
                    tc_buf.append({'id': '', 'type': 'function',
                                   'function': {'name': '', 'arguments': ''}})
                tc = tc_buf[idx]
                if tcd.get('id'):
                    tc['id'] += tcd['id']
                fn = tcd.get('function') or {}
                if fn.get('name'):
                    tc['function']['name'] += fn['name']

                # BUG-FIX #3 : fn.get('arguments') peut être None (certains modèles)
                # avant : tc['function']['arguments'] += fn['arguments'] → TypeError si None
                args_chunk = fn.get('arguments')
                if args_chunk is not None:
                    tc['function']['arguments'] += str(args_chunk)

        # Normalisation finish_reason
        if tc_buf and (finish == 'tool_calls' or any(
            tc['function']['name'] and tc['function']['arguments'] for tc in tc_buf
        )):
            yield {'type': 'tool_calls', 'calls': tc_buf, 'model': model, 'usage': usage}
        else:
            yield {
                'type'     : 'done',
                'text'     : text_buf,
                'reasoning': reasoning_buf,
                'model'    : model,
                'usage'    : usage,
            }
