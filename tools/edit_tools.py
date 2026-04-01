# tools/edit_tools.py — v3
# NEW : multi_str_replace (plusieurs remplacements en un seul appel)
# NEW : insert_lines (insérer des lignes à une position précise)
# IMPROVED : view_file avec meilleur affichage + limite intelligente
import os
from pathlib import Path
from typing import Dict, Any, List


class EditTools:
    MAX_VIEW_LINES = 400   # Au-delà on tronque intelligemment

    def __init__(self, workspace: str):
        self.workspace = Path(os.path.realpath(workspace))

    def _safe_path(self, path: str) -> Path:
        full = Path(os.path.realpath(self.workspace / path))
        ws   = str(self.workspace)
        if not (str(full).startswith(ws + os.sep) or str(full) == ws):
            raise PermissionError(f'Accès interdit hors du workspace: {path}')
        return full

    # ── str_replace ───────────────────────────────────────────────────────────
    def str_replace(self, args: Dict[str, Any]) -> str:
        """Remplace une portion UNIQUE d'un fichier."""
        path    = args.get('path', '')
        old_str = args.get('old_str', '')
        new_str = args.get('new_str', '')
        if not path:        return "Erreur: 'path' requis."
        if old_str == '':   return "Erreur: 'old_str' ne peut pas être vide."
        try:
            safe = self._safe_path(path)
            if not safe.exists(): return f'Fichier non trouvé: {path}'
            content = safe.read_text(encoding='utf-8')
            count   = content.count(old_str)
            if count == 0:
                # Aide : montrer les lignes proches
                lines      = content.split('\n')
                first_line = old_str.split('\n')[0].strip()[:30]
                similar    = [f'  L{i+1}: {l[:80]}'
                              for i, l in enumerate(lines) if first_line and first_line in l]
                hint = ('\n\nLignes similaires:\n' + '\n'.join(similar[:5])) if similar else ''
                return f'Erreur: texte introuvable dans {path}.{hint}'
            if count > 1:
                return (f'Erreur: texte trouvé {count} fois. '
                        'Ajoute plus de contexte pour le rendre unique.')
            safe.write_text(content.replace(old_str, new_str, 1), encoding='utf-8')
            lines_changed = abs(new_str.count('\n') - old_str.count('\n'))
            return f'str_replace OK: {path} ({lines_changed:+d} lignes)'
        except Exception as e:
            return f'Erreur: {e}'

    str_replace.schema = {
        'description': (
            "Remplace une portion UNIQUE d'un fichier. "
            "old_str doit correspondre exactement et n'apparaître qu'une seule fois. "
            "Toujours faire view_file avant."
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'path'   : {'type': 'string'},
                'old_str': {'type': 'string', 'description': 'Texte exact à remplacer (unique dans le fichier)'},
                'new_str': {'type': 'string', 'description': 'Texte de remplacement (peut être vide pour supprimer)'},
            },
            'required': ['path', 'old_str'],
        },
    }

    # ── multi_str_replace ─────────────────────────────────────────────────────
    def multi_str_replace(self, args: Dict[str, Any]) -> str:
        """
        Applique plusieurs remplacements sur un fichier en une seule passe.
        Idéal pour refactoriser plusieurs occurrences d'un même fichier.
        """
        path         = args.get('path', '')
        replacements = args.get('replacements', [])
        if not path:         return "Erreur: 'path' requis."
        if not replacements: return "Erreur: 'replacements' (liste) requis."
        try:
            safe = self._safe_path(path)
            if not safe.exists(): return f'Fichier non trouvé: {path}'
            content  = safe.read_text(encoding='utf-8')
            results  = []
            modified = content

            for i, rep in enumerate(replacements):
                old = rep.get('old_str', '')
                new = rep.get('new_str', '')
                if not old:
                    results.append(f'  [{i}] Ignoré: old_str vide')
                    continue
                count = modified.count(old)
                if count == 0:
                    results.append(f'  [{i}] Introuvable: {repr(old[:40])}')
                elif count > 1 and not rep.get('replace_all', False):
                    results.append(f'  [{i}] {count} occurrences — ajoute replace_all:true pour toutes remplacer')
                else:
                    modified = modified.replace(old, new)
                    results.append(f'  [{i}] OK ({count} occurrence(s) remplacée(s))')

            if modified != content:
                safe.write_text(modified, encoding='utf-8')
            return f'multi_str_replace {path}:\n' + '\n'.join(results)
        except Exception as e:
            return f'Erreur: {e}'

    multi_str_replace.schema = {
        'description': (
            "Applique plusieurs remplacements sur un fichier en une seule opération. "
            "Plus efficace que plusieurs appels str_replace séquentiels."
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string'},
                'replacements': {
                    'type': 'array',
                    'description': 'Liste de {old_str, new_str, replace_all?}',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'old_str'    : {'type': 'string'},
                            'new_str'    : {'type': 'string'},
                            'replace_all': {'type': 'boolean', 'description': 'Remplacer toutes les occurrences (défaut false)'},
                        },
                        'required': ['old_str', 'new_str'],
                    },
                },
            },
            'required': ['path', 'replacements'],
        },
    }

    # ── insert_lines ──────────────────────────────────────────────────────────
    def insert_lines(self, args: Dict[str, Any]) -> str:
        """Insère des lignes à une position précise dans un fichier."""
        path        = args.get('path', '')
        line_number = args.get('line_number')
        content     = args.get('content', '')
        if not path:        return "Erreur: 'path' requis."
        if line_number is None: return "Erreur: 'line_number' requis."
        if not content:     return "Erreur: 'content' requis."
        try:
            safe = self._safe_path(path)
            if not safe.exists(): return f'Fichier non trouvé: {path}'
            lines = safe.read_text(encoding='utf-8').split('\n')
            pos   = max(0, min(int(line_number) - 1, len(lines)))
            new_lines = content.rstrip('\n').split('\n')
            lines[pos:pos] = new_lines
            safe.write_text('\n'.join(lines), encoding='utf-8')
            return f'Inséré {len(new_lines)} ligne(s) à la ligne {pos+1} de {path}'
        except Exception as e:
            return f'Erreur: {e}'

    insert_lines.schema = {
        'description': "Insère des lignes à une position précise dans un fichier sans écraser le contenu.",
        'parameters': {
            'type': 'object',
            'properties': {
                'path'       : {'type': 'string'},
                'line_number': {'type': 'integer', 'description': 'Numéro de ligne AVANT lequel insérer (1-based)'},
                'content'    : {'type': 'string',  'description': 'Contenu à insérer'},
            },
            'required': ['path', 'line_number', 'content'],
        },
    }

    # ── view_file ─────────────────────────────────────────────────────────────
    def view_file(self, args: Dict[str, Any]) -> str:
        """Affiche un fichier avec numéros de ligne."""
        path  = args.get('path', '')
        start = args.get('start_line')
        end   = args.get('end_line')
        if not path: return "Erreur: 'path' requis."
        try:
            safe = self._safe_path(path)
            if not safe.exists(): return f'Non trouvé: {path}'
            if safe.is_dir():
                items = sorted(safe.iterdir())
                lines = [f'  {i.name}{"/" if i.is_dir() else f" ({i.stat().st_size:,}o)"}' for i in items]
                return f'{path}/\n' + '\n'.join(lines)

            content   = safe.read_text(encoding='utf-8')
            all_lines = content.split('\n')
            total     = len(all_lines)

            # Vue partielle
            if start is not None or end is not None:
                s  = max(0, int(start or 1) - 1)
                e  = min(total, int(end or total))
                nb = '\n'.join(f'{s+i+1:4}\t{l}' for i, l in enumerate(all_lines[s:e]))
                return f'{path} (L{s+1}–{e}/{total})\n{nb}'

            # Vue complète avec troncature intelligente
            if total > self.MAX_VIEW_LINES:
                head = '\n'.join(f'{i+1:4}\t{l}' for i, l in enumerate(all_lines[:200]))
                tail = '\n'.join(f'{total-50+i:4}\t{l}' for i, l in enumerate(all_lines[-50:]))
                skipped = total - 250
                return (f'{path} ({total} lignes)\n{head}\n\n'
                        f'  ··· {skipped} lignes masquées — '
                        f'utilise start_line/end_line pour les voir ···\n\n{tail}')

            return (f'{path} ({total} lignes)\n'
                    + '\n'.join(f'{i+1:4}\t{l}' for i, l in enumerate(all_lines)))

        except UnicodeDecodeError:
            return f'Fichier binaire: {path}'
        except Exception as e:
            return f'Erreur: {e}'

    view_file.schema = {
        'description': (
            "Affiche un fichier avec numéros de ligne. "
            "Utilise start_line/end_line pour les gros fichiers. "
            "Indispensable avant str_replace."
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'path'      : {'type': 'string'},
                'start_line': {'type': 'integer', 'description': 'Première ligne (1-based)'},
                'end_line'  : {'type': 'integer', 'description': 'Dernière ligne incluse'},
            },
            'required': ['path'],
        },
    }
