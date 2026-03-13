import subprocess
import shlex
from typing import Dict, Any, Set

class CommandTools:
    ALLOWED_COMMANDS = {
        'ls','cat','grep','find','head','tail','wc','echo','mkdir','rm','cp','mv',
        'chmod','date','pwd','whoami','ps','df','du','uname','uptime','sort','uniq',
        'cut','tr','sed','awk','diff','stat','file','md5sum','sha256sum',
        'zip','unzip','tar','python3','pip','node','npm','curl','wget',
        'ping','netstat','ss','git',
    }

    def __init__(self, workspace: str, allowed_commands: Set[str] = None):
        self.workspace = workspace
        self.allowed_commands = allowed_commands or self.ALLOWED_COMMANDS

    def execute_command(self, args: Dict[str, Any]) -> str:
        """Exécute une commande shell sécurisée (whitelist)."""
        command = args.get('command', '')
        if not command:
            return "Erreur: 'command' requis."
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return f"Erreur parsing: {e}"
        base = parts[0] if parts else ""
        if base not in self.allowed_commands:
            return f"Commande non autorisée: '{base}'. Autorisées: {sorted(self.allowed_commands)}"
        try:
            r = subprocess.run(parts, shell=False, cwd=self.workspace,
                               capture_output=True, text=True, timeout=30)
            lines = []
            if r.stdout.strip():
                lines.append(f"STDOUT:\n{r.stdout.strip()}")
            if r.stderr.strip():
                lines.append(f"STDERR:\n{r.stderr.strip()}")
            lines.append(f"Code: {r.returncode}")
            return "\n".join(lines)
        except subprocess.TimeoutExpired:
            return f"Timeout (30s)."
        except FileNotFoundError:
            return f"Commande '{base}' introuvable."
        except Exception as e:
            return f"Erreur: {e}"
    execute_command.schema = {
        'description': "Exécute une commande shell sécurisée (whitelist).",
        'parameters': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string'}
            },
            'required': ['command']
        }
    }