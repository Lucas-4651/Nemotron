# tools/__init__.py — v3
from tools.file_tools    import FileTools
from tools.code_tools    import CodeTools
from tools.search_tools  import SearchTools
from tools.command_tools import CommandTools
from tools.web_tools     import WebTools
from tools.edit_tools    import EditTools
from typing import Dict, Callable


class ToolManager:
    def __init__(self, workspace_path: str, allowed_commands: set = None,
                 memory_save_cb=None):
        self.workspace     = workspace_path
        self.file_tools    = FileTools(workspace_path)
        self.code_tools    = CodeTools(workspace_path)
        self.search_tools  = SearchTools(workspace_path)
        self.command_tools = CommandTools(workspace_path, allowed_commands)
        self.web_tools     = WebTools()
        self.edit_tools    = EditTools(workspace_path)
        self._memory_save_cb = memory_save_cb

        self._tools = {
            # ── Lecture / Navigation ────────────────────────────────────────
            'project_map'     : self.file_tools.project_map,      # NEW v3
            'view_file'       : self.edit_tools.view_file,
            'read_file'       : self.file_tools.read_file,
            'list_directory'  : self.file_tools.list_directory,
            'find_files'      : self.file_tools.find_files,        # NEW v3
            'get_file_info'   : self.file_tools.get_file_info,
            # ── Édition ─────────────────────────────────────────────────────
            'str_replace'     : self.edit_tools.str_replace,
            'multi_str_replace': self.edit_tools.multi_str_replace, # NEW v3
            'insert_lines'    : self.edit_tools.insert_lines,      # NEW v3
            'write_file'      : self.file_tools.write_file,
            'append_file'     : self.file_tools.append_file,
            # ── Gestion fichiers ─────────────────────────────────────────────
            'move_file'       : self.file_tools.move_file,         # NEW v3
            'create_directory': self.file_tools.create_directory,  # NEW v3
            'delete_path'     : self.file_tools.delete_path,
            # ── Code ────────────────────────────────────────────────────────
            'run_python'      : self.code_tools.run_python,
            'run_node'        : self.code_tools.run_node,
            'run_linter'      : self.code_tools.run_linter,
            'run_tests'       : self.code_tools.run_tests,
            'build_project'   : self.code_tools.build_project,
            'get_dependencies': self.code_tools.get_dependencies,
            # ── Recherche ────────────────────────────────────────────────────
            'grep_files'      : self.search_tools.grep_files,
            'semantic_search' : self.search_tools.semantic_search,
            # ── Web ─────────────────────────────────────────────────────────
            'web_search'      : self.web_tools.web_search,
            'fetch_url'       : self.web_tools.fetch_url,
            # ── Shell ───────────────────────────────────────────────────────
            'execute_command' : self.command_tools.execute_command,
            # ── Mémoire ─────────────────────────────────────────────────────
            'save_memory'     : self._save_memory,
        }

    def _save_memory(self, args: Dict) -> str:
        key = str(args.get('key', '')).strip()
        val = str(args.get('value', '')).strip()
        if not key or not val: return "Erreur: 'key' et 'value' requis."
        if self._memory_save_cb:
            try:
                self._memory_save_cb(key, val)
                return f'Mémoire sauvegardée: {key} = {val}'
            except Exception as e:
                return f'Erreur sauvegarde mémoire: {e}'
        return 'Callback mémoire non disponible.'

    _save_memory.schema = {
        'description': (
            "Sauvegarde une information persistante en mémoire pour les futures sessions. "
            "Utilise pour: préférences utilisateur, nom du projet, stack technique, "
            "décisions importantes, contexte métier."
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'key'  : {'type': 'string', 'description': 'Clé courte snake_case'},
                'value': {'type': 'string', 'description': 'Valeur à retenir'},
            },
            'required': ['key', 'value'],
        },
    }

    def get_all_tools(self) -> Dict[str, Callable]:
        return self._tools

    def get_openrouter_tools_spec(self) -> list:
        schemas = []
        for name, func in self._tools.items():
            # Chercher le schema sur la fonction (méthode ou fonction liée)
            schema = getattr(func, 'schema', None)
            if schema is None:
                # Méthode liée : chercher sur __func__
                schema = getattr(getattr(func, '__func__', None), 'schema', None)
            if schema:
                schemas.append({
                    'type'    : 'function',
                    'function': {
                        'name'       : name,
                        'description': schema['description'],
                        'parameters' : schema['parameters'],
                    }
                })
            else:
                schemas.append({
                    'type'    : 'function',
                    'function': {
                        'name'       : name,
                        'description': f'Outil {name}',
                        'parameters' : {'type': 'object', 'properties': {}},
                    }
                })
        return schemas
