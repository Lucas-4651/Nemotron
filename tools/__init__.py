# tools/__init__.py
from tools.file_tools import FileTools
from tools.code_tools import CodeTools
from tools.search_tools import SearchTools
from tools.command_tools import CommandTools
from tools.web_tools import WebTools
from tools.edit_tools import EditTools
from typing import Dict, Callable


class ToolManager:
    def __init__(self, workspace_path: str, allowed_commands: set = None):
        self.workspace = workspace_path
        self.file_tools = FileTools(workspace_path)
        self.code_tools = CodeTools(workspace_path)
        self.search_tools = SearchTools(workspace_path)
        self.command_tools = CommandTools(workspace_path, allowed_commands)
        self.web_tools = WebTools()
        self.edit_tools = EditTools(workspace_path)

        self._tools = {
            'read_file':        self.file_tools.read_file,
            'write_file':       self.file_tools.write_file,
            'append_file':      self.file_tools.append_file,
            'list_directory':   self.file_tools.list_directory,
            'delete_path':      self.file_tools.delete_path,
            'get_file_info':    self.file_tools.get_file_info,
            'str_replace':      self.edit_tools.str_replace,
            'view_file':        self.edit_tools.view_file,
            'run_python':       self.code_tools.run_python,
            'run_node':         self.code_tools.run_node,
            'run_linter':       self.code_tools.run_linter,
            'run_tests':        self.code_tools.run_tests,
            'build_project':    self.code_tools.build_project,
            'get_dependencies': self.code_tools.get_dependencies,
            'grep_files':       self.search_tools.grep_files,
            'semantic_search':  self.search_tools.semantic_search,
            'web_search':       self.web_tools.web_search,
            'fetch_url':        self.web_tools.fetch_url,
            'execute_command':  self.command_tools.execute_command,
        }

    def get_all_tools(self) -> Dict[str, Callable]:
        return self._tools

    def get_openrouter_tools_spec(self) -> list:
        schemas = []
        for name, func in self._tools.items():
            if hasattr(func, 'schema'):
                schemas.append({
                    'type': 'function',
                    'function': {
                        'name': name,
                        'description': func.schema['description'],
                        'parameters': func.schema['parameters']
                    }
                })
            else:
                schemas.append({
                    'type': 'function',
                    'function': {
                        'name': name,
                        'description': f"Outil {name}",
                        'parameters': {'type': 'object', 'properties': {}}
                    }
                })
        return schemas