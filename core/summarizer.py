# core/summarizer.py — v4.0
# BUG-FIX mineur : len(history) comptait aussi les messages 'tool' et 'assistant' tool_calls
# → seuil de résumé atteint trop tôt. On ne compte que les échanges user/assistant texte.
import logging
from typing import List, Dict

from core.llm_client import LLMClient
from config import Config

logger = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def summarize_history(self, history: List[Dict]) -> str:
        if not history:
            return ''
        conv_text = '\n'.join(
            f"{m['role'].upper()}: {str(m.get('content', ''))[:400]}"
            for m in history
            if isinstance(m.get('content'), str) and m.get('role') in ('user', 'assistant')
        )
        if not conv_text.strip():
            return ''
        prompt   = f"Résume en 150 mots max : tâches, actions, fichiers créés.\n\n{conv_text}"
        messages = [{'role': 'user', 'content': prompt}]
        return self.llm.simple_call(messages, profile='summary') or ''

    def summarize_if_needed(self, history: List[Dict]) -> str:
        """
        BUG-FIX : ne compter que les messages conversationnels (user + assistant texte)
        pour le seuil, pas les messages 'tool' ou assistant avec tool_calls.
        Cela aligne le seuil sur ce que l'utilisateur perçoit comme "longueur de conv".
        """
        ctx_win = Config.CONTEXT_WINDOW

        # Messages conversationnels uniquement (pas les tool results)
        conversational = [
            m for m in history
            if m.get('role') in ('user', 'assistant')
            and isinstance(m.get('content'), str)
            and m.get('content', '').strip()
        ]

        if len(conversational) > ctx_win:
            # Résumer tout sauf les ctx_win derniers messages conversationnels
            # Retrouver leurs index dans history pour garder la cohérence
            recent_conv = set(id(m) for m in conversational[-ctx_win:])
            to_summarize = [m for m in history if id(m) not in recent_conv]
            return self.summarize_history(to_summarize)
        return ''
