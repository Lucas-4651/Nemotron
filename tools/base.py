from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTool(ABC):
    @abstractmethod
    def __call__(self, args: Dict[str, Any]) -> str:
        pass

    @property
    def schema(self) -> dict:
        """Retourne le schéma OpenRouter pour cet outil."""
        return {
            'description': self.__doc__ or "Outil",
            'parameters': {
                'type': 'object',
                'properties': {},
                'required': []
            }
        }