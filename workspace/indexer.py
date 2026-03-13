import chromadb
from chromadb.config import Settings
from pathlib import Path
import hashlib
from typing import List, Dict, Any, Optional
import os

class CodeIndexer:
    def __init__(self, workspace_path: Path, persist_dir: str = "./chroma_db"):
        self.workspace = workspace_path
        self.client = chromadb.PersistentClient(path=persist_dir)
        # Nom de collection unique basé sur le chemin absolu du workspace
        collection_name = f"ws_{hashlib.md5(str(workspace_path.absolute()).encode()).hexdigest()}"
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def index_file(self, file_path: Path):
        """Ajoute ou met à jour un fichier dans l'index."""
        rel_path = str(file_path.relative_to(self.workspace))
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            print(f"Erreur lecture {file_path}: {e}")
            return
        # Découpage en chunks
        chunks = self._chunk_content(content)
        ids = [f"{rel_path}#{i}" for i in range(len(chunks))]
        metadatas = [{"path": rel_path, "chunk": i} for i in range(len(chunks))]
        # Supprimer les anciennes entrées pour ce fichier
        self.collection.delete(where={"path": rel_path})
        if chunks:
            self.collection.add(
                documents=chunks,
                metadatas=metadatas,
                ids=ids
            )

    def index_directory(self, path: Optional[Path] = None):
        """Indexe récursivement tous les fichiers texte."""
        base = path or self.workspace
        for root, _, files in os.walk(base):
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in {'.py', '.js', '.ts', '.json', '.txt', '.md', '.html', '.css', '.sh', '.yaml', '.yml', '.sql'}:
                    self.index_file(Path(root) / file)

    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Recherche sémantique par similarité."""
        results = self.collection.query(query_texts=[query], n_results=n_results)
        out = []
        for i in range(len(results['ids'][0])):
            out.append({
                'path': results['metadatas'][0][i]['path'],
                'chunk': results['metadatas'][0][i]['chunk'],
                'content': results['documents'][0][i],
                'score': results['distances'][0][i] if 'distances' in results else None
            })
        return out

    def _chunk_content(self, content: str, max_chars: int = 1500) -> List[str]:
        """Découpe en chunks de taille raisonnable pour l'embedding."""
        lines = content.splitlines()
        chunks = []
        current = []
        current_len = 0
        for line in lines:
            line_len = len(line) + 1
            if current_len + line_len > max_chars and current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += line_len
        if current:
            chunks.append("\n".join(current))
        return chunks