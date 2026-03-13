# tools/web_tools.py
import urllib.request
import urllib.parse
import urllib.error
import json
import re
from typing import Dict, Any


class WebTools:
    def __init__(self):
        self.headers = {'User-Agent': 'Mozilla/5.0 (compatible; Nemotron-Agent/1.0)'}

    def _request(self, url, method='GET', headers=None, body=None, timeout=15):
        req_headers = {**self.headers, **(headers or {})}
        data = body.encode('utf-8') if body else None
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read()
                content_type = resp.headers.get('Content-Type', '')
                status = resp.status
                try:
                    text = content.decode('utf-8')
                except UnicodeDecodeError:
                    text = content.decode('latin-1', errors='replace')
                return status, content_type, text
        except urllib.error.HTTPError as e:
            return e.code, '', f"HTTP Error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return 0, '', f"URL Error: {e.reason}"
        except Exception as e:
            return 0, '', f"Erreur: {e}"

    def web_search(self, args: Dict[str, Any]) -> str:
        """Recherche des informations sur le web via DuckDuckGo."""
        query = args.get('query', '').strip()
        n = min(int(args.get('n_results', 5)), 10)
        if not query:
            return "Erreur: 'query' requis."
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        status, ctype, text = self._request(url)
        if status == 0:
            return f"Recherche impossible: {text}"
        try:
            data = json.loads(text)
        except:
            return "Erreur parsing resultats."
        results = []
        if data.get('AbstractText'):
            results.append(f"[REPONSE DIRECTE] {data.get('Heading', query)}\n{data['AbstractText']}\nSource: {data.get('AbstractURL', '')}")
        if data.get('Answer'):
            results.append(f"[REPONSE] {data['Answer']}")
        for topic in data.get('RelatedTopics', []):
            if len(results) >= n:
                break
            if isinstance(topic, dict) and topic.get('Text') and topic.get('FirstURL'):
                results.append(f"- {topic['Text'][:200]}\n  {topic['FirstURL']}")
        if not results:
            return f"Aucun resultat pour: {query}\nEssaie fetch_url avec une URL directe."
        return f"=== {query} ===\n\n" + '\n\n'.join(results[:n])

    web_search.schema = {
        'description': "Recherche des informations sur le web (DuckDuckGo).",
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'La requete de recherche'},
                'n_results': {'type': 'integer', 'description': 'Nombre de resultats (defaut 5)'}
            },
            'required': ['query']
        }
    }

    def fetch_url(self, args: Dict[str, Any]) -> str:
        """Recupere le contenu d'une URL (API, doc, endpoint)."""
        url = args.get('url', '').strip()
        method = args.get('method', 'GET').upper()
        headers = args.get('headers', {})
        body = args.get('body', None)
        max_chars = int(args.get('max_chars', 6000))
        if not url:
            return "Erreur: 'url' requis."
        if not url.startswith(('http://', 'https://')):
            return "Erreur: URL doit commencer par http:// ou https://"
        status, content_type, text = self._request(url, method=method, headers=headers, body=body)
        if status == 0:
            return f"Impossible de joindre: {url}\n{text}"
        if 'application/json' in content_type:
            try:
                formatted = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
                if len(formatted) > max_chars:
                    formatted = formatted[:max_chars] + '\n... [tronque]'
                return f"[HTTP {status}] {url}\n\n{formatted}"
            except:
                pass
        if 'text/html' in content_type:
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + '\n... [tronque]'
        return f"[HTTP {status}] {url}\n\n{text}"

    fetch_url.schema = {
        'description': "Recupere le contenu d'une URL (API, documentation, endpoint).",
        'parameters': {
            'type': 'object',
            'properties': {
                'url': {'type': 'string'},
                'method': {'type': 'string', 'description': 'GET, POST, PUT, DELETE'},
                'headers': {'type': 'object'},
                'body': {'type': 'string'},
                'max_chars': {'type': 'integer'}
            },
            'required': ['url']
        }
    }