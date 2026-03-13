import os
import shutil
from pathlib import Path
from typing import Optional, List

class WorkspaceManager:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.current: Optional[Path] = None

    def list_workspaces(self) -> List[str]:
        return [d.name for d in self.root.iterdir() if d.is_dir()]

    def create_workspace(self, name: str) -> Path:
        path = self.root / name
        path.mkdir(exist_ok=True)
        return path

    def delete_workspace(self, name: str):
        path = self.root / name
        if path.exists():
            shutil.rmtree(path)

    def switch_workspace(self, name: str) -> Path:
        path = self.root / name
        if not path.exists():
            path.mkdir()
        self.current = path
        return path

    def get_current_path(self) -> Optional[Path]:
        return self.current

    def get_absolute_path(self, relative: str) -> Path:
        if not self.current:
            raise RuntimeError("Aucun workspace actif")
        full = (self.current / relative).resolve()
        # sécurité
        if not str(full).startswith(str(self.current.resolve())):
            raise PermissionError("Accès hors workspace")
        return full