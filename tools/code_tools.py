import subprocess
import tempfile
import os
import json
from pathlib import Path
from typing import Dict, Any

class CodeTools:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace).resolve()

    def run_python(self, args: Dict[str, Any]) -> str:
        """Exécute du code Python."""
        code = args.get('code', '')
        timeout = int(args.get('timeout', 15))
        if not code:
            return "Erreur: 'code' requis."
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            r = subprocess.run(['python3', tmp], cwd=self.workspace,
                               capture_output=True, text=True, timeout=timeout)
            out = []
            if r.stdout:
                out.append(f"STDOUT:\n{r.stdout.strip()}")
            if r.stderr:
                out.append(f"STDERR:\n{r.stderr.strip()}")
            out.append(f"Code: {r.returncode}")
            return "\n".join(out)
        except subprocess.TimeoutExpired:
            return f"Timeout ({timeout}s)."
        except FileNotFoundError:
            return "python3 introuvable."
        except Exception as e:
            return f"Erreur: {e}"
        finally:
            os.unlink(tmp)
    run_python.schema = {
        'description': "Exécute du code Python 3 et retourne stdout + stderr.",
        'parameters': {
            'type': 'object',
            'properties': {
                'code': {'type': 'string', 'description': 'Code Python complet'},
                'timeout': {'type': 'integer', 'description': 'Timeout secondes (défaut 15)'}
            },
            'required': ['code']
        }
    }

    def run_node(self, args: Dict[str, Any]) -> str:
        """Exécute du code JavaScript avec Node.js."""
        code = args.get('code', '')
        timeout = int(args.get('timeout', 15))
        if not code:
            return "Erreur: 'code' requis."
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            r = subprocess.run(['node', tmp], cwd=self.workspace,
                               capture_output=True, text=True, timeout=timeout)
            out = []
            if r.stdout:
                out.append(f"STDOUT:\n{r.stdout.strip()}")
            if r.stderr:
                out.append(f"STDERR:\n{r.stderr.strip()}")
            out.append(f"Code: {r.returncode}")
            return "\n".join(out)
        except subprocess.TimeoutExpired:
            return f"Timeout ({timeout}s)."
        except FileNotFoundError:
            return "Node.js introuvable. Installe: pkg install nodejs"
        except Exception as e:
            return f"Erreur: {e}"
        finally:
            os.unlink(tmp)
    run_node.schema = {
        'description': "Exécute du code JavaScript avec Node.js et retourne stdout + stderr.",
        'parameters': {
            'type': 'object',
            'properties': {
                'code': {'type': 'string', 'description': 'Code JS complet'},
                'timeout': {'type': 'integer', 'description': 'Timeout secondes (défaut 15)'}
            },
            'required': ['code']
        }
    }

    def run_linter(self, args: Dict[str, Any]) -> str:
        """Exécute un linter (pylint, eslint) sur un fichier ou dossier."""
        path = args.get('path', '.')
        lang = args.get('lang', 'python')
        full_path = self.workspace / path
        if not full_path.exists():
            return f"Chemin introuvable: {path}"
        if lang == 'python':
            cmd = ['pylint', str(full_path)]
        elif lang == 'javascript':
            cmd = ['npx', 'eslint', str(full_path)]
        else:
            return f"Langage non supporté: {lang}"
        try:
            r = subprocess.run(cmd, cwd=self.workspace,
                               capture_output=True, text=True, timeout=30)
            out = r.stdout + r.stderr
            return out if out else "Aucun problème détecté."
        except subprocess.TimeoutExpired:
            return "Timeout du linter."
        except FileNotFoundError:
            return f"Linter {cmd[0]} non installé."
        except Exception as e:
            return f"Erreur: {e}"
    run_linter.schema = {
        'description': "Exécute un linter (pylint, eslint) sur un fichier ou dossier.",
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Chemin relatif (défaut: .)'},
                'lang': {'type': 'string', 'description': 'python ou javascript (défaut python)'}
            },
            'required': []
        }
    }

    def run_tests(self, args: Dict[str, Any]) -> str:
        """Exécute les tests (pytest, jest)."""
        framework = args.get('framework', 'pytest')
        path = args.get('path', 'tests')
        full_path = self.workspace / path
        if not full_path.exists():
            return f"Chemin introuvable: {path}"
        if framework == 'pytest':
            cmd = ['pytest', str(full_path), '-v']
        elif framework == 'jest':
            cmd = ['npx', 'jest', str(full_path)]
        else:
            return f"Framework non supporté: {framework}"
        try:
            r = subprocess.run(cmd, cwd=self.workspace,
                               capture_output=True, text=True, timeout=60)
            return r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return "Timeout des tests."
        except FileNotFoundError:
            return f"Framework {cmd[0]} non installé."
        except Exception as e:
            return f"Erreur: {e}"
    run_tests.schema = {
        'description': "Exécute les tests (pytest, jest).",
        'parameters': {
            'type': 'object',
            'properties': {
                'framework': {'type': 'string', 'description': 'pytest ou jest (défaut pytest)'},
                'path': {'type': 'string', 'description': 'Chemin vers les tests (défaut tests)'}
            },
            'required': []
        }
    }

    def build_project(self, args: Dict[str, Any]) -> str:
        """Lance une commande de build (ex: npm run build, make)."""
        cmd = args.get('command', '')
        if not cmd:
            return "Commande manquante."
        try:
            r = subprocess.run(cmd, shell=True, cwd=self.workspace,
                               capture_output=True, text=True, timeout=120)
            return r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return "Timeout du build."
        except Exception as e:
            return f"Erreur: {e}"
    build_project.schema = {
        'description': "Lance une commande de build (ex: npm run build, make).",
        'parameters': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string', 'description': 'Commande shell à exécuter'}
            },
            'required': ['command']
        }
    }

    def get_dependencies(self, args: Dict[str, Any]) -> str:
        """Lit les dépendances depuis package.json ou requirements.txt."""
        type_ = args.get('type', 'auto')
        if type_ == 'auto':
            if (self.workspace / 'package.json').exists():
                type_ = 'npm'
            elif (self.workspace / 'requirements.txt').exists():
                type_ = 'pip'
            else:
                return "Aucun fichier de dépendances reconnu."
        if type_ == 'npm':
            try:
                with open(self.workspace / 'package.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                deps = data.get('dependencies', {})
                devDeps = data.get('devDependencies', {})
                return f"Dépendances: {len(deps)} prod, {len(devDeps)} dev"
            except Exception as e:
                return f"Erreur lecture package.json: {e}"
        elif type_ == 'pip':
            try:
                with open(self.workspace / 'requirements.txt', 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]
                return f"Dépendances: {len(lines)} paquets"
            except Exception as e:
                return f"Erreur lecture requirements.txt: {e}"
        else:
            return "Type inconnu."
    get_dependencies.schema = {
        'description': "Lit les dépendances depuis package.json ou requirements.txt.",
        'parameters': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'description': 'npm, pip, ou auto (défaut auto)'}
            },
            'required': []
        }
    }