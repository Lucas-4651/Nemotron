import requests
import json
import time
import logging
from typing import List, Dict, Optional, Generator, Any
from config import Config

logger = logging.getLogger(__name__)

class LLMClient:
    API_URL = 'https://openrouter.ai/api/v1/chat/completions'

    def __init__(self, api_key: str, model: str, fallbacks: List[str]):
        self.api_key = api_key
        self.model = model
        self.fallbacks = fallbacks
        self.timeouts = Config.MODEL_TIMEOUTS

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://lucas46-agent.onrender.com',
            'X-Title': 'Lucas46 Dev Agent',
        }

    def _timeout_for(self, model: str) -> int:
        return self.timeouts.get(model, Config.DEFAULT_TIMEOUT)

    def _payload(self, messages: List[dict], model: str,
                 tools_spec: Optional[List] = None,
                 stream: bool = False,
                 reasoning: bool = False) -> dict:
        p = {
            'model': model,
            'messages': messages,
            'temperature': 0.2,
            'stream': stream,
        }
        p['reasoning'] = {'effort': 'high'} if reasoning else {'exclude': True}
        if tools_spec:
            p['tools'] = tools_spec
            p['tool_choice'] = 'auto'
        return p

    def simple_call(self, messages: List[dict], reasoning: bool = False) -> Optional[str]:
        """Appel non-streaming pour résumé ou autres."""
        if not self.api_key:
            return None
        for model in [self.model] + self.fallbacks:
            try:
                resp = requests.post(
                    self.API_URL,
                    headers=self._headers(),
                    json=self._payload(messages, model, None, False, reasoning),
                    timeout=self._timeout_for(model),
                )
                if resp.status_code in (401, 429, 500):
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data['choices'][0]['message'].get('content', '')
            except Exception as e:
                logger.warning(f"simple_call {model}: {e}")
        return None

    def stream_call(self, messages: List[dict], tools_spec: Optional[List],
                    reasoning: bool = False) -> Generator[dict, None, None]:
        """Générateur d'événements : token, tool_calls, done, error."""
        if not self.api_key:
            yield {'type': 'error', 'text': 'Clé API manquante'}
            return

        queue = [self.model] + [m for m in self.fallbacks if m != self.model]
        for model in queue:
            timeout = self._timeout_for(model)
            payload = self._payload(messages, model, tools_spec, stream=True, reasoning=reasoning)
            try:
                with requests.post(
                    self.API_URL,
                    headers=self._headers(),
                    json=payload,
                    stream=True,
                    timeout=timeout,
                ) as resp:
                    if resp.status_code == 401:
                        yield {'type': 'error', 'text': 'Clé API invalide (401)'}
                        return
                    if resp.status_code == 429:
                        time.sleep(2)
                        continue
                    if resp.status_code >= 500:
                        logger.warning(f"{resp.status_code} on {model}")
                        continue
                    resp.raise_for_status()

                    text_buf = ""
                    tc_buf = []
                    usage = {}
                    finish = ""

                    for line in resp.iter_lines():
                        if not line:
                            continue
                        line = line.decode('utf-8') if isinstance(line, bytes) else line
                        if line.startswith(': '):
                            continue
                        if line == 'data: [DONE]':
                            break
                        if not line.startswith('data: '):
                            continue
                        try:
                            chunk = json.loads(line[6:])
                        except:
                            continue

                        if chunk.get('usage'):
                            usage = chunk['usage']
                        choices = chunk.get('choices') or []
                        if not choices:
                            continue
                        delta = choices[0].get('delta') or {}
                        finish = choices[0].get('finish_reason') or finish

                        tok = delta.get('content') or ''
                        if tok:
                            text_buf += tok
                            yield {'type': 'token', 'text': tok}

                        for tcd in delta.get('tool_calls') or []:
                            idx = tcd.get('index', 0)
                            while len(tc_buf) <= idx:
                                tc_buf.append({
                                    'id': '',
                                    'type': 'function',
                                    'function': {'name': '', 'arguments': ''}
                                })
                            tc = tc_buf[idx]
                            if tcd.get('id'):
                                tc['id'] += tcd['id']
                            fn = tcd.get('function') or {}
                            if fn.get('name'):
                                tc['function']['name'] += fn['name']
                            if fn.get('arguments'):
                                tc['function']['arguments'] += fn['arguments']

                    if finish == 'tool_calls' and tc_buf:
                        yield {'type': 'tool_calls', 'calls': tc_buf, 'model': model, 'usage': usage}
                    else:
                        yield {'type': 'done', 'text': text_buf, 'model': model, 'usage': usage}
                    return

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout ({timeout}s) on {model}")
                continue
            except Exception as e:
                logger.error(f"Stream error {model}: {e}")
                continue

        yield {'type': 'error', 'text': 'Tous les modèles ont échoué.'}