
# SKILL: API REST / OpenRouter / Fetch / Webhooks

## Protocole obligatoire
1. `fetch_url` sur l'endpoint pour voir la structure réelle avant d'intégrer
2. Tester avec un appel minimal avant d'écrire le code complet
3. Ne jamais hardcoder les clés API → toujours `os.environ.get()`
4. Toujours gérer les cas d'erreur (timeout, 429, 5xx)

---

## OpenRouter — appels LLM (Python)

```python
# llm/openrouter.py
import requests
import json
import time

OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'

def chat(messages, model='qwen/qwen3-coder:free', stream=False,
         tools=None, api_key=None, timeout=90):
    headers = {
        'Authorization': f"Bearer {api_key or os.environ['OPENROUTER_API_KEY']}",
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://mon-projet.onrender.com',
        'X-Title': 'Mon Agent',
    }
    payload = {
        'model': model,
        'messages': messages,
        'temperature': 0.2,
        'stream': stream,
    }
    if tools:
        payload['tools'] = tools
        payload['tool_choice'] = 'auto'

    r = requests.post(OPENROUTER_URL, headers=headers,
                      json=payload, stream=stream, timeout=timeout)
    r.raise_for_status()
    return r

def chat_simple(messages, model='qwen/qwen3-coder:free', **kwargs):
    """Appel non-streaming, retourne le texte directement."""
    r = chat(messages, model, stream=False, **kwargs)
    return r.json()['choices'][0]['message']['content']
```

## OpenRouter — streaming SSE (Python)

```python
def stream_chat(messages, model, tools=None, **kwargs):
    """Générateur d'événements SSE depuis OpenRouter."""
    r = chat(messages, model, stream=True, tools=tools, **kwargs)
    text_buf = ''
    tc_buf = []

    for line in r.iter_lines():
        if not line: continue
        line = line.decode('utf-8') if isinstance(line, bytes) else line
        if line == 'data: [DONE]': break
        if not line.startswith('data: '): continue
        try:
            chunk = json.loads(line[6:])
        except: continue

        choices = chunk.get('choices') or []
        if not choices: continue
        delta = choices[0].get('delta') or {}
        finish = choices[0].get('finish_reason')

        # Token texte
        if delta.get('content'):
            text_buf += delta['content']
            yield {'type': 'token', 'text': delta['content']}

        # Tool calls (streaming progressif)
        for tcd in delta.get('tool_calls') or []:
            idx = tcd.get('index', 0)
            while len(tc_buf) <= idx:
                tc_buf.append({'id':'','type':'function','function':{'name':'','arguments':''}})
            tc = tc_buf[idx]
            if tcd.get('id'): tc['id'] += tcd['id']
            fn = tcd.get('function') or {}
            if fn.get('name'): tc['function']['name'] += fn['name']
            if fn.get('arguments'): tc['function']['arguments'] += fn['arguments']

        if finish == 'tool_calls' and tc_buf:
            yield {'type': 'tool_calls', 'calls': tc_buf}
            return
        elif finish == 'stop':
            yield {'type': 'done', 'text': text_buf}
            return
```

## OpenRouter — streaming (Node.js)

```javascript
// utils/openrouter.js
export async function* streamChat(messages, model, tools = null, apiKey) {
  const res = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey || process.env.OPENROUTER_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model, messages, stream: true, temperature: 0.2,
      ...(tools && { tools, tool_choice: 'auto' })
    })
  })

  if (!res.ok) throw new Error(`OpenRouter ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()

    for (const line of lines) {
      if (!line.startsWith('data: ') || line === 'data: [DONE]') continue
      try {
        const chunk = JSON.parse(line.slice(6))
        const delta = chunk.choices?.[0]?.delta
        if (delta?.content) yield { type: 'token', text: delta.content }
        if (chunk.choices?.[0]?.finish_reason === 'stop') return
      } catch {}
    }
  }
}
```

## Définition d'outils (tool use)

```python
# Format OpenRouter / OpenAI compatible
TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'read_file',
            'description': 'Lit le contenu d\'un fichier texte.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'Chemin du fichier'}
                },
                'required': ['path']
            }
        }
    }
]
```

## REST API — client générique Python

```python
import requests
import time

class APIClient:
    def __init__(self, base_url, api_key=None, timeout=30):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        if api_key:
            self.session.headers['Authorization'] = f'Bearer {api_key}'
        self.timeout = timeout

    def get(self, path, **kwargs):
        return self._request('GET', path, **kwargs)

    def post(self, path, **kwargs):
        return self._request('POST', path, **kwargs)

    def _request(self, method, path, retries=3, **kwargs):
        url = f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault('timeout', self.timeout)
        for attempt in range(1, retries + 1):
            try:
                r = self.session.request(method, url, **kwargs)
                if r.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                return r.json() if 'json' in r.headers.get('Content-Type','') else r.text
            except requests.exceptions.Timeout:
                if attempt == retries: raise
            except requests.exceptions.RequestException:
                if attempt == retries: raise
                time.sleep(attempt)
```

## Webhook — recevoir et valider

```python
# Valider un webhook avec signature HMAC
import hmac, hashlib

@app.route('/webhook', methods=['POST'])
def webhook():
    sig = request.headers.get('X-Signature-256', '')
    secret = os.environ['WEBHOOK_SECRET'].encode()
    expected = 'sha256=' + hmac.new(secret, request.data, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return {'error': 'Signature invalide'}, 401
    data = request.json
    # traiter data...
    return {'ok': True}
```

## Variables d'env — pattern sécurisé

```python
# Ne JAMAIS faire:
api_key = "sk-ant-xxxx"

# TOUJOURS faire:
api_key = os.environ.get('ANTHROPIC_API_KEY')
if not api_key:
    raise ValueError("ANTHROPIC_API_KEY manquante")
```

## Render — variables d'environnement

- Ajouter dans le dashboard Render → Environment
- Jamais dans le code ou .env commité
- `os.environ.get('KEY', 'default')` pour les non-critiques
- `os.environ['KEY']` pour les critiques (lève une erreur si absente)

## Erreurs courantes

- `401 Unauthorized` → clé API invalide ou mal formatée (vérifier le Bearer)
- `429 Too Many Requests` → rate limit, implémenter exponential backoff
- `503 Service Unavailable` → modèle OpenRouter surchargé, utiliser fallback
- `JSONDecodeError` → réponse non-JSON reçue, logger `r.text` pour debug
- `SSLError` → certificat invalide, `verify=False` en dev seulement
- `ConnectionTimeout` → augmenter le timeout ou réduire la payload
