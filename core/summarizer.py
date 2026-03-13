import logging
from typing import List, Dict
from core.llm_client import LLMClient

logger = logging.getLogger(__name__)

class Summarizer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def summarize_history(self, history: List[Dict]) -> str:
        """Génère un résumé de l'historique."""
        if not history:
            return ""
        conv_text = "\n".join(
            f"{m['role'].upper()}: {str(m.get('content', ''))[:400]}"
            for m in history if isinstance(m.get('content'), str)
        )
        prompt = f"Résume en 150 mots max : tâches, actions, fichiers créés.\n\n{conv_text}"
        messages = [{'role': 'user', 'content': prompt}]
        return self.llm.simple_call(messages) or ""

    def summarize_if_needed(self, history: List[Dict], max_tokens: int = 8000) -> str:
        """Retourne un résumé si l'historique dépasse le seuil."""
        # Ici on pourrait estimer les tokens, mais on simplifie
        if len(history) > 20:  # seuil arbitraire
            return self.summarize_history(history[:-10])
        return ""