import os
import shutil
import stat
from datetime import datetime
from typing import Dict, Any


class FileTools:
    def __init__(self, workspace: str):
        # os.path.realpath résout les liens symboliques ET les composants '..'.
        self.workspace = os.path.realpath(workspace)

    def _safe_path(self, path: str) -> str:
        # BUG-04 FIX : os.path.abspath() ne résout PAS les symlinks.
        # Un lien symbolique dans le workspace pointant vers /etc passerait
        # le check startswith(workspace). os.path.realpath() résout d'abord
        # tous les liens avant de vérifier la frontière du workspace.
        full = os.path.realpath(os.path.join(self.workspace, path))
        if not full.startswith(self.workspace + os.sep) and full != self.workspace:
            raise PermissionError(f"Accès interdit hors de {self.workspace}: {path}")
        return full

    # ------------------------------------------------------------------
    # read_file
    # ------------------------------------------------------------------
    def read_file(self, args: Dict[str, Any]) -> str:
        """Lit le contenu d'un fichier."""
        path = args.get('path', '')
        if not path:
            return "Erreur: 'path' requis."
        try:
            with open(self._safe_path(path), 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            return f"Fichier binaire ou encodage non-UTF8: {path}"
        except Exception as e:
            return f"Erreur lecture: {e}"

    read_file.schema = {
        'description': "Lit le contenu complet d'un fichier texte.",
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Chemin relatif du fichier'},
            },
            'required': ['path'],
        },
    }

    # ------------------------------------------------------------------
    # write_file
    # ------------------------------------------------------------------
    def write_file(self, args: Dict[str, Any]) -> str:
        """Écrit ou écrase un fichier."""
        path    = args.get('path', '')
        content = args.get('content', '')
        if not path:
            return "Erreur: 'path' requis."
        try:
            safe = self._safe_path(path)
            os.makedirs(os.path.dirname(safe) or self.workspace, exist_ok=True)
            with open(safe, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Fichier écrit: {path} ({os.path.getsize(safe)} octets)"
        except Exception as e:
            return f"Erreur écriture: {e}"

    write_file.schema = {
        'description': "Écrit (ou écrase) un fichier. Crée les dossiers parents si nécessaire.",
        'parameters': {
            'type': 'object',
            'properties': {
                'path':    {'type': 'string'},
                'content': {'type': 'string'},
            },
            'required': ['path', 'content'],
        },
    }

    # ------------------------------------------------------------------
    # append_file
    # ------------------------------------------------------------------
    def append_file(self, args: Dict[str, Any]) -> str:
        """Ajoute du contenu à la fin d'un fichier."""
        path    = args.get('path', '')
        content = args.get('content', '')
        if not path:
            return "Erreur: 'path' requis."
        try:
            safe = self._safe_path(path)
            os.makedirs(os.path.dirname(safe) or self.workspace, exist_ok=True)
            with open(safe, 'a', encoding='utf-8') as f:
                f.write(content)
            return f"Contenu ajouté à: {path}"
        except Exception as e:
            return f"Erreur append: {e}"

    append_file.schema = {
        'description': "Ajoute du contenu à la fin d'un fichier sans l'écraser.",
        'parameters': {
            'type': 'object',
            'properties': {
                'path':    {'type': 'string'},
                'content': {'type': 'string'},
            },
            'required': ['path', 'content'],
        },
    }

    # ------------------------------------------------------------------
    # list_directory
    # ------------------------------------------------------------------
    def list_directory(self, args: Dict[str, Any]) -> str:
        """Liste le contenu d'un répertoire."""
        path = args.get('path', '.')
        try:
            safe  = self._safe_path(path)
            items = sorted(os.listdir(safe))
            if not items:
                return "Répertoire vide."
            result = []
            for item in items:
                full   = os.path.join(safe, item)
                marker = "/" if os.path.isdir(full) else ""
                try:
                    size = "" if os.path.isdir(full) else f" ({os.path.getsize(full)}o)"
                except OSError:
                    size = ""
                result.append(f"{item}{marker}{size}")
            return "\n".join(result)
        except Exception as e:
            return f"Erreur listage: {e}"

    list_directory.schema = {
        'description': "Liste le contenu d'un répertoire avec tailles.",
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': "Chemin (défaut: '.')"},
            },
            'required': [],
        },
    }

    # ------------------------------------------------------------------
    # delete_path
    # ------------------------------------------------------------------
    def delete_path(self, args: Dict[str, Any]) -> str:
        """Supprime un fichier ou répertoire."""
        path = args.get('path', '')
        if not path:
            return "Erreur: 'path' requis."
        try:
            safe = self._safe_path(path)
            if os.path.isdir(safe):
                shutil.rmtree(safe)
            else:
                os.remove(safe)
            return f"Supprimé: {path}"
        except Exception as e:
            return f"Erreur suppression: {e}"

    delete_path.schema = {
        'description': "Supprime un fichier ou répertoire (récursivement). IRRÉVERSIBLE.",
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string'},
            },
            'required': ['path'],
        },
    }

    # ------------------------------------------------------------------
    # get_file_info
    # ------------------------------------------------------------------
    def get_file_info(self, args: Dict[str, Any]) -> str:
        """Métadonnées d'un fichier."""
        path = args.get('path', '')
        if not path:
            return "Erreur: 'path' requis."
        try:
            safe  = self._safe_path(path)
            s     = os.stat(safe)
            mtime = datetime.fromtimestamp(s.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            perms = stat.filemode(s.st_mode)
            ftype = "répertoire" if os.path.isdir(safe) else "fichier"
            return (
                f"Type: {ftype}\n"
                f"Taille: {s.st_size} octets\n"
                f"Modifié: {mtime}\n"
                f"Permissions: {perms}"
            )
        except Exception as e:
            return f"Erreur info: {e}"

    get_file_info.schema = {
        'description': "Métadonnées d'un fichier : taille, date modification, permissions.",
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string'},
            },
            'required': ['path'],
        },
    }
