import subprocess
import shlex
from pathlib import Path
from typing import Dict, Any

class SearchTools:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace).resolve()
        # L'indexeur est optionnel, peut être attaché plus tard
        self.indexer = None

    def set_indexer(self, indexer):
        self.indexer = indexer

    def grep_files(self, args: Dict[str, Any]) -> str:
        """Recherche regex avec grep."""
        pattern = args.get('pattern', '')
        path = args.get('path', '.')
        if not pattern:
            return "Pattern requis."
        full_path = self.workspace / path
        if not full_path.exists():
            return f"Chemin introuvable: {path}"
        cmd = f"grep -rnE {shlex.quote(pattern)} {shlex.quote(str(full_path))}"
        try:
            r = subprocess.run(cmd, shell=True, cwd=self.workspace,
                               capture_output=True, text=True, timeout=30)
            out = r.stdout if r.stdout else r.stderr
            return out if out else "Aucune correspondance."
        except subprocess.TimeoutExpired:
            return "Timeout grep."
        except Exception as e:
            return f"Erreur: {e}"
    grep_files.schema = {
        'description': "Cherche un pattern regex dans les fichiers d'un répertoire.",
        'parameters': {
            'type': 'object',
            'properties': {
                'pattern': {'type': 'string', 'description': 'Expression régulière'},
                'path': {'type': 'string', 'description': 'Chemin (défaut: .)'}
            },
            'required': ['pattern']
        }
    }

    def semantic_search(self, args: Dict[str, Any]) -> str:
        """Recherche par similarité sémantique via l'index."""
        if not self.indexer:
            return "Indexeur non disponible. Veuillez d'abord indexer le projet."
        query = args.get('query', '')
        n = int(args.get('n_results', 5))
        if not query:
            return "Query requise."
        results = self.indexer.search(query, n_results=n)
        if not results:
            return "Aucun résultat trouvé."
        out_lines = []
        for r in results:
            out_lines.append(f"{r['path']} (score: {r.get('score', 0):.2f}):")
            out_lines.append(r['content'][:200] + "...")
        return "\n\n".join(out_lines)
    semantic_search.schema = {
        'description': "Recherche par similarité sémantique dans le code (nécessite indexation préalable).",
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Requête en langage naturel'},
                'n_results': {'type': 'integer', 'description': 'Nombre de résultats (défaut 5)'}
            },
            'required': ['query']
        }
    }