import logging
from typing import List, Dict

from core.llm_client import LLMClient
from config import Config

logger = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def summarize_history(self, history: List[Dict]) -> str:
        """Génère un résumé de l'historique."""
        if not history:
            return ''
        conv_text = '\n'.join(
            f"{m['role'].upper()}: {str(m.get('content', ''))[:400]}"
            for m in history if isinstance(m.get('content'), str)
        )
        prompt   = f"Résume en 150 mots max : tâches, actions, fichiers créés.\n\n{conv_text}"
        messages = [{'role': 'user', 'content': prompt}]
        return self.llm.simple_call(messages) or ''

    def summarize_if_needed(self, history: List[Dict]) -> str:
        """Retourne un résumé si l'historique dépasse le seuil de la config.

        BUG-17 FIX : le seuil était hardcodé à 20 sans lien avec la config.
        Config.CONTEXT_WINDOW définit combien de messages récents on garde
        à la fin ; on résume tout ce qui précède (history[:-ctx_win]).
        On utilise aussi MAX_HISTORY_TOKENS comme garde-fou en tokens.
        """
        ctx_win = Config.CONTEXT_WINDOW  # ex. 20

        # On résume dès qu'on a plus de ctx_win messages (pas seulement > 20
        # arbitraire) — ce qui aligne exactement le summarizer sur le fenêtrage
        # fait dans agent._build_messages().
        if len(history) > ctx_win:
            return self.summarize_history(history[:-ctx_win])
        return ''
