# tools/web_tools.py — v3
# IMPROVED : web_search avec 3 stratégies de fallback
#   1. DuckDuckGo Instant Answer API
#   2. DuckDuckGo HTML scraping
#   3. Brave Search API (si clé dispo)
import urllib.request
import urllib.parse
import urllib.error
import json
import re
import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class WebTools:
    UA = 'Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0'

    def __init__(self):
        self._brave_key = os.environ.get('BRAVE_SEARCH_API_KEY', '')

    def _get(self, url: str, headers: dict = None, timeout: int = 15) -> tuple:
        """Retourne (status, content_type, text)."""
        h = {'User-Agent': self.UA, **(headers or {})}
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw  = r.read()
                ct   = r.headers.get('Content-Type', '')
                try:   text = raw.decode('utf-8')
                except: text = raw.decode('latin-1', errors='replace')
                return r.status, ct, text
        except urllib.error.HTTPError as e:
            return e.code, '', f'HTTP {e.code}: {e.reason}'
        except Exception as e:
            return 0, '', str(e)

    # ── web_search ─────────────────────────────────────────────────────────
    def web_search(self, args: Dict[str, Any]) -> str:
        query = args.get('query', '').strip()
        n     = min(int(args.get('n_results', 5)), 10)
        if not query:
            return "Erreur: 'query' requis."

        # Stratégie 1 : Brave Search (si clé dispo)
        if self._brave_key:
            result = self._brave_search(query, n)
            if result:
                return result

        # Stratégie 2 : DDG Instant Answer
        result = self._ddg_api(query, n)
        if result and 'Aucun résultat' not in result:
            return result

        # Stratégie 3 : DDG HTML scraping
        result = self._ddg_html(query, n)
        if result:
            return result

        return f'Aucun résultat pour: {query}\nEssaie fetch_url avec une URL directe.'

    def _ddg_api(self, query: str, n: int) -> str:
        url    = f'https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1'
        status, ct, text = self._get(url, timeout=10)
        if status == 0:
            return ''
        try:
            data    = json.loads(text)
            results = []
            if data.get('AbstractText'):
                results.append(
                    f"[Réponse directe] {data.get('Heading', query)}\n"
                    f"{data['AbstractText']}\nSource: {data.get('AbstractURL', '')}"
                )
            if data.get('Answer'):
                results.append(f"[Réponse] {data['Answer']}")
            for topic in data.get('RelatedTopics', []):
                if len(results) >= n:
                    break
                if isinstance(topic, dict) and topic.get('Text') and topic.get('FirstURL'):
                    results.append(f"- {topic['Text'][:200]}\n  {topic['FirstURL']}")
            if not results:
                return ''
            return f'=== {query} ===\n\n' + '\n\n'.join(results[:n])
        except Exception:
            return ''

    def _ddg_html(self, query: str, n: int) -> str:
        """Scrape les résultats HTML de DuckDuckGo."""
        url    = f'https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}'
        status, ct, html = self._get(url, timeout=12)
        if status == 0 or not html:
            return ''
        # Extraire les résultats : <a class="result__a" href="...">title</a>
        # et les snippets : <a class="result__snippet">...</a>
        results: List[str] = []
        # Nettoyage HTML basique
        html_clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html_clean = re.sub(r'<style[^>]*>.*?</style>',  '', html_clean, flags=re.DOTALL)

        # Chercher les blocs résultat
        blocks = re.findall(
            r'<a class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'(?:<a class="result__snippet"[^>]*>(.*?)</a>)?',
            html_clean, re.DOTALL
        )
        for href, title, snippet in blocks[:n]:
            title   = re.sub(r'<[^>]+>', '', title).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet or '').strip()
            # DDG encode les URLs en base64-like, prendre le paramètre uddg
            real_url = href
            m = re.search(r'uddg=([^&]+)', href)
            if m:
                try:    real_url = urllib.parse.unquote(m.group(1))
                except: pass
            if title:
                results.append(f'- {title}\n  {snippet}\n  {real_url}')

        if not results:
            return ''
        return f'=== {query} ===\n\n' + '\n\n'.join(results)

    def _brave_search(self, query: str, n: int) -> str:
        url    = f'https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}&count={n}'
        status, ct, text = self._get(url, headers={
            'Accept'             : 'application/json',
            'Accept-Encoding'    : 'gzip, deflate',
            'X-Subscription-Token': self._brave_key,
        }, timeout=12)
        if status != 200:
            return ''
        try:
            data    = json.loads(text)
            results = []
            for item in data.get('web', {}).get('results', [])[:n]:
                results.append(
                    f"- {item.get('title', '')}\n"
                    f"  {item.get('description', '')}\n"
                    f"  {item.get('url', '')}"
                )
            return f'=== {query} (Brave) ===\n\n' + '\n\n'.join(results) if results else ''
        except Exception as e:
            logger.warning(f'Brave search parse error: {e}')
            return ''

    web_search.schema = {
        'description': "Recherche des informations sur le web (DDG + Brave fallback).",
        'parameters' : {
            'type': 'object',
            'properties': {
                'query'    : {'type': 'string'},
                'n_results': {'type': 'integer', 'description': 'Nombre de résultats (défaut 5)'},
            },
            'required': ['query'],
        },
    }

    # ── fetch_url ──────────────────────────────────────────────────────────
    def fetch_url(self, args: Dict[str, Any]) -> str:
        url       = args.get('url', '').strip()
        method    = args.get('method', 'GET').upper()
        headers   = args.get('headers', {})
        body      = args.get('body')
        max_chars = int(args.get('max_chars', 8000))
        if not url:
            return "Erreur: 'url' requis."
        if not url.startswith(('http://', 'https://')):
            return "URL doit commencer par http:// ou https://"

        req_headers = {'User-Agent': self.UA, **headers}
        data = body.encode('utf-8') if body else None
        req  = urllib.request.Request(url, data=data, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                ct  = r.headers.get('Content-Type', '')
                try:   text = raw.decode('utf-8')
                except: text = raw.decode('latin-1', errors='replace')

                if 'application/json' in ct:
                    try:
                        fmt = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
                        return f'[HTTP {r.status}] {url}\n\n{fmt[:max_chars]}'
                    except Exception:
                        pass
                if 'text/html' in ct:
                    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                    text = re.sub(r'<style[^>]*>.*?</style>',   '', text, flags=re.DOTALL)
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                return f'[HTTP {r.status}] {url}\n\n{text[:max_chars]}'

        except urllib.error.HTTPError as e:
            return f'HTTP {e.code}: {e.reason} — {url}'
        except Exception as e:
            return f'Erreur fetch: {e}'

    fetch_url.schema = {
        'description': "Récupère le contenu d'une URL (API, documentation, page web).",
        'parameters' : {
            'type': 'object',
            'properties': {
                'url'      : {'type': 'string'},
                'method'   : {'type': 'string', 'description': 'GET, POST, PUT, DELETE'},
                'headers'  : {'type': 'object'},
                'body'     : {'type': 'string'},
                'max_chars': {'type': 'integer', 'description': 'Limite caractères (défaut 8000)'},
            },
            'required': ['url'],
        },
    }
