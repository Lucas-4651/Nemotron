# tools/file_tools.py — v3
# NEW : move_file, create_directory, find_files, project_map
import os
import shutil
import stat
import fnmatch
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List


class FileTools:
    IGNORE_DIRS  = {'.git', 'node_modules', '__pycache__', '.venv', 'venv',
                    'dist', 'build', '.next', '.nuxt', 'coverage'}
    IGNORE_FILES = {'.DS_Store', 'Thumbs.db', '*.pyc', '*.pyo', '*.class'}

    def __init__(self, workspace: str):
        self.workspace = os.path.realpath(workspace)

    def _safe_path(self, path: str) -> str:
        full = os.path.realpath(os.path.join(self.workspace, path))
        if not full.startswith(self.workspace + os.sep) and full != self.workspace:
            raise PermissionError(f'Accès interdit hors du workspace: {path}')
        return full

    # ── read_file ─────────────────────────────────────────────────────────────
    def read_file(self, args: Dict[str, Any]) -> str:
        path = args.get('path', '')
        if not path: return "Erreur: 'path' requis."
        try:
            with open(self._safe_path(path), 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            return f'Fichier binaire ou encodage non-UTF8: {path}'
        except Exception as e:
            return f'Erreur lecture: {e}'

    read_file.schema = {
        'description': "Lit le contenu complet d'un fichier texte.",
        'parameters' : {'type': 'object',
                        'properties': {'path': {'type': 'string', 'description': 'Chemin relatif'}},
                        'required': ['path']},
    }

    # ── write_file ────────────────────────────────────────────────────────────
    def write_file(self, args: Dict[str, Any]) -> str:
        path    = args.get('path', '')
        content = args.get('content', '')
        if not path: return "Erreur: 'path' requis."
        try:
            safe = self._safe_path(path)
            os.makedirs(os.path.dirname(safe) or self.workspace, exist_ok=True)
            with open(safe, 'w', encoding='utf-8') as f:
                f.write(content)
            return f'Fichier écrit: {path} ({os.path.getsize(safe)} octets)'
        except Exception as e:
            return f'Erreur écriture: {e}'

    write_file.schema = {
        'description': "Écrit (ou écrase) un fichier. Préférer str_replace pour des modifications partielles.",
        'parameters' : {'type': 'object',
                        'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}},
                        'required': ['path', 'content']},
    }

    # ── append_file ───────────────────────────────────────────────────────────
    def append_file(self, args: Dict[str, Any]) -> str:
        path    = args.get('path', '')
        content = args.get('content', '')
        if not path: return "Erreur: 'path' requis."
        try:
            safe = self._safe_path(path)
            os.makedirs(os.path.dirname(safe) or self.workspace, exist_ok=True)
            with open(safe, 'a', encoding='utf-8') as f:
                f.write(content)
            return f'Contenu ajouté à: {path}'
        except Exception as e:
            return f'Erreur append: {e}'

    append_file.schema = {
        'description': "Ajoute du contenu à la fin d'un fichier sans l'écraser.",
        'parameters' : {'type': 'object',
                        'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}},
                        'required': ['path', 'content']},
    }

    # ── move_file ─────────────────────────────────────────────────────────────
    def move_file(self, args: Dict[str, Any]) -> str:
        """Déplace ou renomme un fichier/dossier."""
        src = args.get('src', '')
        dst = args.get('dst', '')
        if not src or not dst: return "Erreur: 'src' et 'dst' requis."
        try:
            safe_src = self._safe_path(src)
            safe_dst = self._safe_path(dst)
            if not os.path.exists(safe_src):
                return f'Source introuvable: {src}'
            os.makedirs(os.path.dirname(safe_dst) or self.workspace, exist_ok=True)
            shutil.move(safe_src, safe_dst)
            return f'Déplacé: {src} → {dst}'
        except Exception as e:
            return f'Erreur déplacement: {e}'

    move_file.schema = {
        'description': "Déplace ou renomme un fichier ou dossier dans le workspace.",
        'parameters' : {'type': 'object',
                        'properties': {'src': {'type': 'string', 'description': 'Chemin source'},
                                       'dst': {'type': 'string', 'description': 'Chemin destination'}},
                        'required': ['src', 'dst']},
    }

    # ── create_directory ──────────────────────────────────────────────────────
    def create_directory(self, args: Dict[str, Any]) -> str:
        """Crée un répertoire (et ses parents si nécessaire)."""
        path = args.get('path', '')
        if not path: return "Erreur: 'path' requis."
        try:
            safe = self._safe_path(path)
            os.makedirs(safe, exist_ok=True)
            return f'Répertoire créé: {path}'
        except Exception as e:
            return f'Erreur création répertoire: {e}'

    create_directory.schema = {
        'description': "Crée un répertoire et tous ses parents si nécessaire.",
        'parameters' : {'type': 'object',
                        'properties': {'path': {'type': 'string'}},
                        'required': ['path']},
    }

    # ── list_directory ────────────────────────────────────────────────────────
    def list_directory(self, args: Dict[str, Any]) -> str:
        path = args.get('path', '.')
        try:
            safe  = self._safe_path(path)
            items = sorted(os.listdir(safe))
            if not items: return 'Répertoire vide.'
            result = []
            for item in items:
                full   = os.path.join(safe, item)
                marker = '/' if os.path.isdir(full) else ''
                try:   size = '' if os.path.isdir(full) else f' ({os.path.getsize(full):,}o)'
                except: size = ''
                result.append(f'{item}{marker}{size}')
            return '\n'.join(result)
        except Exception as e:
            return f'Erreur listage: {e}'

    list_directory.schema = {
        'description': "Liste le contenu d'un répertoire avec tailles.",
        'parameters' : {'type': 'object',
                        'properties': {'path': {'type': 'string', 'description': "Chemin (défaut: '.')"}},
                        'required': []},
    }

    # ── delete_path ───────────────────────────────────────────────────────────
    def delete_path(self, args: Dict[str, Any]) -> str:
        path = args.get('path', '')
        if not path: return "Erreur: 'path' requis."
        try:
            safe = self._safe_path(path)
            if os.path.isdir(safe): shutil.rmtree(safe)
            else:                   os.remove(safe)
            return f'Supprimé: {path}'
        except Exception as e:
            return f'Erreur suppression: {e}'

    delete_path.schema = {
        'description': "Supprime un fichier ou répertoire (récursivement). IRRÉVERSIBLE.",
        'parameters' : {'type': 'object',
                        'properties': {'path': {'type': 'string'}},
                        'required': ['path']},
    }

    # ── get_file_info ─────────────────────────────────────────────────────────
    def get_file_info(self, args: Dict[str, Any]) -> str:
        path = args.get('path', '')
        if not path: return "Erreur: 'path' requis."
        try:
            safe  = self._safe_path(path)
            s     = os.stat(safe)
            mtime = datetime.fromtimestamp(s.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            perms = stat.filemode(s.st_mode)
            ftype = 'répertoire' if os.path.isdir(safe) else 'fichier'
            return (f'Type: {ftype}\nTaille: {s.st_size:,} octets\n'
                    f'Modifié: {mtime}\nPermissions: {perms}')
        except Exception as e:
            return f'Erreur info: {e}'

    get_file_info.schema = {
        'description': "Métadonnées d'un fichier : taille, date, permissions.",
        'parameters' : {'type': 'object',
                        'properties': {'path': {'type': 'string'}},
                        'required': ['path']},
    }

    # ── find_files ────────────────────────────────────────────────────────────
    def find_files(self, args: Dict[str, Any]) -> str:
        """Cherche des fichiers par nom/pattern dans le workspace."""
        pattern  = args.get('pattern', '*')
        path     = args.get('path', '.')
        max_res  = int(args.get('max_results', 50))
        try:
            safe    = self._safe_path(path)
            matches = []
            for root, dirs, files in os.walk(safe):
                dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS and not d.startswith('.')]
                for fname in files:
                    if fnmatch.fnmatch(fname, pattern) or fnmatch.fnmatch(fname.lower(), pattern.lower()):
                        rel = os.path.relpath(os.path.join(root, fname), self.workspace)
                        matches.append(rel)
                        if len(matches) >= max_res:
                            break
                if len(matches) >= max_res:
                    break
            if not matches:
                return f'Aucun fichier correspondant à "{pattern}".'
            result = '\n'.join(matches)
            if len(matches) >= max_res:
                result += f'\n... (limité à {max_res} résultats)'
            return result
        except Exception as e:
            return f'Erreur find_files: {e}'

    find_files.schema = {
        'description': "Cherche des fichiers par nom ou pattern glob (ex: *.py, config*) dans le workspace.",
        'parameters' : {'type': 'object',
                        'properties': {
                            'pattern'    : {'type': 'string', 'description': 'Pattern glob (ex: *.py, *.json)'},
                            'path'       : {'type': 'string', 'description': 'Dossier de départ (défaut: .)'},
                            'max_results': {'type': 'integer', 'description': 'Max résultats (défaut 50)'},
                        },
                        'required': ['pattern']},
    }

    # ── project_map ───────────────────────────────────────────────────────────
    def project_map(self, args: Dict[str, Any]) -> str:
        """
        Génère un arbre complet du projet avec tailles.
        Essentiel pour comprendre un gros projet rapidement.
        """
        path       = args.get('path', '.')
        max_depth  = int(args.get('max_depth', 4))
        show_sizes = args.get('show_sizes', True)
        try:
            safe = self._safe_path(path)
            lines: List[str] = []
            total_files = [0]
            total_size  = [0]

            def _walk(p: str, prefix: str, depth: int):
                if depth > max_depth:
                    return
                try:
                    entries = sorted(os.listdir(p))
                except PermissionError:
                    return
                dirs  = [e for e in entries if os.path.isdir(os.path.join(p, e))
                         and e not in self.IGNORE_DIRS and not e.startswith('.')]
                files = [e for e in entries if os.path.isfile(os.path.join(p, e))
                         and not any(fnmatch.fnmatch(e, ig) for ig in self.IGNORE_FILES)]

                for i, d in enumerate(dirs):
                    connector = '└── ' if (i == len(dirs) - 1 and not files) else '├── '
                    lines.append(f'{prefix}{connector}{d}/')
                    ext = '    ' if connector.startswith('└') else '│   '
                    _walk(os.path.join(p, d), prefix + ext, depth + 1)

                for i, f in enumerate(files):
                    connector = '└── ' if i == len(files) - 1 else '├── '
                    fpath     = os.path.join(p, f)
                    try:
                        sz = os.path.getsize(fpath)
                        total_files[0] += 1
                        total_size[0]  += sz
                        size_str = f'  ({sz:,}o)' if show_sizes else ''
                    except Exception:
                        size_str = ''
                    lines.append(f'{prefix}{connector}{f}{size_str}')

            rel = os.path.relpath(safe, self.workspace) if safe != self.workspace else '.'
            lines.append(f'{rel}/')
            _walk(safe, '', 1)

            summary = (f'\n── {total_files[0]} fichiers, '
                       f'{total_size[0]/1024:.1f} KB total ──')
            return '\n'.join(lines) + summary

        except Exception as e:
            return f'Erreur project_map: {e}'

    project_map.schema = {
        'description': (
            "Génère l'arbre complet du projet avec tailles. "
            "Utilise en PREMIER pour comprendre la structure avant d'intervenir."
        ),
        'parameters' : {'type': 'object',
                        'properties': {
                            'path'      : {'type': 'string', 'description': "Racine (défaut: .)"},
                            'max_depth' : {'type': 'integer', 'description': 'Profondeur max (défaut 4)'},
                            'show_sizes': {'type': 'boolean', 'description': 'Afficher les tailles (défaut true)'},
                        },
                        'required': []},
    }
