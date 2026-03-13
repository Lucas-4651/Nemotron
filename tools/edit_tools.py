# tools/edit_tools.py
import os
from pathlib import Path
from typing import Dict, Any


class EditTools:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace).resolve()

    def _safe_path(self, path: str) -> Path:
        full = (self.workspace / path).resolve()
        if not str(full).startswith(str(self.workspace)):
            raise PermissionError(f"Acces interdit hors du workspace: {path}")
        return full

    def str_replace(self, args: Dict[str, Any]) -> str:
        """Remplace une portion unique d'un fichier."""
        path = args.get('path', '')
        old_str = args.get('old_str', '')
        new_str = args.get('new_str', '')
        if not path:
            return "Erreur: 'path' requis."
        if old_str == '':
            return "Erreur: 'old_str' ne peut pas etre vide."
        try:
            safe = self._safe_path(path)
            if not safe.exists():
                return f"Fichier non trouve: {path}"
            content = safe.read_text(encoding='utf-8')
            count = content.count(old_str)
            if count == 0:
                lines = content.split('\n')
                first_line = old_str.split('\n')[0].strip()[:20]
                similar = [f"  Ligne {i+1}: {l[:80]}" for i, l in enumerate(lines) if first_line in l]
                hint = ('\n\nLignes similaires:\n' + '\n'.join(similar[:5])) if similar else ''
                return f"Erreur: texte introuvable dans {path}.{hint}"
            if count > 1:
                return f"Erreur: texte trouve {count} fois. Ajoute plus de contexte pour le rendre unique."
            safe.write_text(content.replace(old_str, new_str, 1), encoding='utf-8')
            return f"str_replace OK sur {path}"
        except Exception as e:
            return f"Erreur: {e}"

    str_replace.schema = {
        'description': "Remplace une portion UNIQUE d'un fichier. old_str doit correspondre exactement et etre unique.",
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string'},
                'old_str': {'type': 'string', 'description': 'Texte exact a remplacer (unique dans le fichier)'},
                'new_str': {'type': 'string', 'description': 'Texte de remplacement'}
            },
            'required': ['path', 'old_str']
        }
    }

    def view_file(self, args: Dict[str, Any]) -> str:
        """Affiche un fichier avec numeros de ligne."""
        path = args.get('path', '')
        start = args.get('start_line')
        end = args.get('end_line')
        if not path:
            return "Erreur: 'path' requis."
        try:
            safe = self._safe_path(path)
            if not safe.exists():
                return f"Non trouve: {path}"
            if safe.is_dir():
                items = sorted(safe.iterdir())
                lines = [f"  {i.name}{'/' if i.is_dir() else f' ({i.stat().st_size}o)'}" for i in items]
                return f"{path}/\n" + '\n'.join(lines)
            content = safe.read_text(encoding='utf-8')
            all_lines = content.split('\n')
            total = len(all_lines)
            if start is not None or end is not None:
                s = max(0, int(start or 1) - 1)
                e = min(total, int(end or total))
                numbered = '\n'.join(f"{s+i+1}\t{l}" for i, l in enumerate(all_lines[s:e]))
                return f"{path} (lignes {s+1}-{e}/{total})\n{numbered}"
            MAX = 300
            if total > MAX:
                head = '\n'.join(f"{i+1}\t{l}" for i, l in enumerate(all_lines[:150]))
                tail = '\n'.join(f"{total-50+i}\t{l}" for i, l in enumerate(all_lines[-50:]))
                return f"{path} ({total} lignes)\n{head}\n\n... [{total-200} lignes] ...\n\n{tail}"
            return f"{path} ({total} lignes)\n" + '\n'.join(f"{i+1}\t{l}" for i, l in enumerate(all_lines))
        except UnicodeDecodeError:
            return f"Fichier binaire: {path}"
        except Exception as e:
            return f"Erreur: {e}"

    view_file.schema = {
        'description': "Affiche un fichier avec numeros de ligne. Utilise avant str_replace.",
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string'},
                'start_line': {'type': 'integer'},
                'end_line': {'type': 'integer'}
            },
            'required': ['path']
        }
    }