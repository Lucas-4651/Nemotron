# core/agent.py
import json
import logging
import threading
from typing import List, Dict, Generator

from core.llm_client import LLMClient
from core.tool_cache import ToolCache
from core.metrics import SessionMetrics
from core.summarizer import Summarizer
from core.skill_loader import SkillLoader
from tools import ToolManager
from config import Config

logger = logging.getLogger(__name__)

BASE_SYSTEM = """
Tu es Nemotron, agent IA expert en développement logiciel créé par Lucas46 Tech Studio.

Environnement:
- Termux / Proot Debian
- Python / Node.js / Bash
- Express / Flask
- PostgreSQL / SQLite
- Render / GitHub Actions

Règles:
- Toujours lire avant modifier
- Préférer str_replace à write_file
- Tester avant livrer
- Utiliser tools pour vérifier
- Réponses concises
"""

class DevAgent:

    def __init__(self, workspace_path: str, config: dict=None):

        self.config = config or {}

        self.workspace_path = workspace_path
        self.api_key = self.config.get("api_key") or Config.OPENROUTER_API_KEY
        self.model = self.config.get("model", Config.DEFAULT_MODEL)
        self.fallbacks = self.config.get("fallback_models", Config.FREE_FALLBACKS)

        self.max_steps = self.config.get("max_steps", Config.MAX_STEPS)
        self.max_htoks = self.config.get("max_history_tokens", Config.MAX_HISTORY_TOKENS)
        self.ctx_win = self.config.get("context_window", Config.CONTEXT_WINDOW)

        self.max_tools_per_step = self.config.get("max_tools_per_step", 2)
        self.tool_timeout = self.config.get("tool_timeout", 5)

        self.llm = LLMClient(self.api_key, self.model, self.fallbacks)

        self.cache = ToolCache(workspace_path=workspace_path)
        self.metrics = SessionMetrics()
        self.summarizer = Summarizer(self.llm)
        self.skill_loader = SkillLoader()

        self.tool_mgr = ToolManager(
            workspace_path,
            self.config.get("allowed_commands")
        )

        self.tools_fn = self.tool_mgr.get_all_tools()
        self.tools_spec = self.tool_mgr.get_openrouter_tools_spec()

        self.history: List[Dict] = []
        self.history_tokens = 0

        self.reasoning_enabled = False
        self.memory_context = ""

    # -----------------------------------------------------

    def _est_tokens(self, text:str)->int:
        return int(len(str(text).split())*1.3)

    def _add_history(self, role:str, content:str, extra:dict=None):

        msg = {"role":role,"content":content}

        if extra:
            msg.update(extra)

        self.history.append(msg)

        if content:
            self.history_tokens += self._est_tokens(content)

    # -----------------------------------------------------

    def _smart_history(self):

        filtered=[]

        for m in reversed(self.history):

            if m["role"] in ("assistant","tool","user"):
                filtered.append(m)

            if len(filtered)>=self.ctx_win:
                break

        filtered.reverse()

        return filtered

    # -----------------------------------------------------

    def _build_system(self,user_message:str=""):

        parts=[BASE_SYSTEM]

        if self.memory_context:
            parts.append(f"[MEMOIRE]\n{self.memory_context}")

        try:

            skill_context=self.skill_loader.get_context(
                user_message,
                history=self.history,
                max_skills=2,
                min_score=2
            )

            if skill_context:
                parts.append(skill_context)

        except Exception as e:
            logger.warning(f"Skill error {e}")

        return "\n\n---\n\n".join(parts)

    # -----------------------------------------------------

    def _build_messages(self,system:str):

        msgs=[{"role":"system","content":system}]

        try:

            if self.history_tokens>self.max_htoks:

                summary=self.summarizer.summarize_if_needed(self.history)

                if summary:
                    msgs.append({"role":"system","content":f"[RESUME]\n{summary}"})

                msgs.extend(self._smart_history())

            else:
                msgs.extend(self._smart_history())

        except Exception as e:

            logger.warning(f"build_messages error {e}")
            msgs.extend(self._smart_history())

        return msgs

    # -----------------------------------------------------

    def _run_tool(self,fn,args):

        if fn is None:
            return "outil inconnu"

        result=[None]

        def target():

            try:
                result[0]=str(fn(args))
            except Exception as e:
                result[0]=f"Erreur outil {e}"

        t=threading.Thread(target=target,daemon=True)

        t.start()
        t.join(self.tool_timeout)

        if t.is_alive():
            return f"Timeout {self.tool_timeout}s"

        return result[0] or "Aucun resultat"

    # -----------------------------------------------------

    def _run_tools_parallel(self,tool_calls):

        threads=[]
        results=[None]*len(tool_calls)

        def run_tool(i,tc):

            name=tc["function"].get("name","unknown")

            try:
                args=json.loads(tc["function"].get("arguments","{}"))
            except:
                args={}

            cached=self.cache.get(name,args)

            if cached is not None:
                results[i]=(name,cached,True)
                return

            fn=self.tools_fn.get(name)

            r=self._run_tool(fn,args)

            self.cache.set(name,args,r)

            results[i]=(name,r,False)

        for i,tc in enumerate(tool_calls):

            t=threading.Thread(target=run_tool,args=(i,tc))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        return results

    # -----------------------------------------------------

    def stream_task(self,user_input:str)->Generator[dict,None,None]:

        self._add_history("user",user_input)

        system=self._build_system(user_input)

        try:

            detected=self.skill_loader.detect_skills(
                user_input,
                self.history[:-1]
            )

            active=[fn.replace(".md","") for fn,s in detected if s>=2][:2]

            if active:
                yield {"type":"skill","skills":active}

        except Exception as e:
            logger.warning(f"detect skills error {e}")

        # -----------------------------------------------------

        for step in range(1,self.max_steps+1):

            messages=self._build_messages(system)

            yield {"type":"thinking","step":step,"max":self.max_steps}

            tool_calls=None
            final_text=""
            model_used=self.model

            try:

                for ev in self.llm.stream_call(
                    messages,
                    self.tools_spec,
                    self.reasoning_enabled
                ):

                    if ev["type"]=="token":

                        final_text+=ev["text"]

                        yield {"type":"token","text":ev["text"]}

                    elif ev["type"]=="tool_calls":

                        tool_calls=ev["calls"][:self.max_tools_per_step]

                        model_used=ev.get("model",self.model)

                        self.metrics.add_req(ev.get("usage",{}))

                        break

                    elif ev["type"]=="done":

                        final_text=ev.get("text","")

                        model_used=ev.get("model",self.model)

                        self.metrics.add_req(ev.get("usage",{}))

                        break

                    elif ev["type"]=="error":

                        self._add_history("assistant",ev.get("text",""))

                        yield {"type":"error","text":ev.get("text","Erreur")}

                        return

            except Exception as e:

                yield {"type":"error","text":f"LLM error {e}"}
                return

            # -----------------------------------------------------

            if tool_calls:

                self.history.append({
                    "role":"assistant",
                    "content":None,
                    "tool_calls":tool_calls
                })

                yield {"type":"tool_batch","count":len(tool_calls)}

                results=self._run_tools_parallel(tool_calls)

                for name,result,cached in results:

                    self.metrics.add_tool(name,cached)

                    yield {
                        "type":"tool_result",
                        "name":name,
                        "result":result[:2000],
                        "cached":cached
                    }

                    self.history.append({
                        "role":"tool",
                        "name":name,
                        "content":result
                    })

                continue

            # -----------------------------------------------------

            self._add_history("assistant",final_text)

            yield {
                "type":"done",
                "model":model_used,
                "metrics":self.metrics.to_dict()
            }

            return

        yield {"type":"error","text":"max steps atteint"}