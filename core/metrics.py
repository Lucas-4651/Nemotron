import json
import os
from datetime import datetime
from typing import Dict

class SessionMetrics:
    def __init__(self):
        self.start = datetime.now()
        self.tin = 0
        self.tout = 0
        self.cost = 0.0
        self.reqs = 0
        self.errors = 0
        self.tools = 0
        self.cache_hits = 0
        self.tool_use: Dict[str, int] = {}

    def add_req(self, usage: dict):
        self.reqs += 1
        self.tin += usage.get('prompt_tokens', 0)
        self.tout += usage.get('completion_tokens', 0)
        self.cost += usage.get('total_cost', 0.0)

    def add_tool(self, name: str, cached: bool = False):
        self.tools += 1
        if cached:
            self.cache_hits += 1
        self.tool_use[name] = self.tool_use.get(name, 0) + 1

    def to_dict(self) -> dict:
        return {
            'requests': self.reqs,
            'tokens_in': self.tin,
            'tokens_out': self.tout,
            'cost_usd': round(self.cost, 8),
            'tools': self.tools,
            'cache_hits': self.cache_hits,
            'tool_usage': self.tool_use,
            'errors': self.errors,
            'duration_s': round((datetime.now() - self.start).total_seconds(), 1),
        }