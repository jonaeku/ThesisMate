from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import END, MessageGraph

from src.agents.research import ResearchAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.structure import StructureAgent
from src.agents.topic_scout import TopicScoutAgent
from src.agents.writing import WritingAssistantAgent

from src.utils.config import get_env
from src.utils.logging import get_logger
from src.utils.openrouter_client import OpenRouterClient
from src.utils.gemini_client import GeminiClient
import os
import re
print("Current working dir:", os.getcwd())

logger = get_logger(__name__)

class Orchestrator:
    def __init__(self):
        #self.api_key = get_env("OPENROUTER_API_KEY")
        #logger.info(f"API Key: {self.api_key}")
        #self.client = OpenRouterClient()
        self.client = GeminiClient(model="gemini-1.5-flash") 
        
        # Keep agents for future enhancement
        self.topic_scout = TopicScoutAgent()
        self.research_agent = ResearchAgent(
            local_root="./thesis",
            github_owner="jonaeku",
            github_repo="ThesisMate",
            github_path="",      # Optional: Unterordner im Repo, z.B. "papers"
            github_ref="main",   # Branch/Ref; nimm "main", wenn dein Default-Branch so heißt
            # github_token=os.getenv("GITHUB_TOKEN"),  # nur nötig für private Repos/höhere Limits
       )
        self.structure_agent = StructureAgent(research_agent=self.research_agent)
        self.writing_assistant = WritingAssistantAgent()
        self.reviewer_agent = ReviewerAgent()

        self.graph = MessageGraph()
        self.graph.add_node("router", self._router)
        self.graph.add_node("topic_scout", self.topic_scout.respond)
        self.graph.add_node("research_agent", self.research_agent.respond)
        self.graph.add_node("structure_agent", lambda msgs: self.structure_agent.respond(msgs, adapt=True))
        self.graph.add_node("writing_assistant", lambda msgs: self.writing_assistant.chat_node(msgs, self.research_agent))
        self.graph.add_node("reviewer_agent", self.reviewer_agent.respond)

        self.graph.add_conditional_edges(
                    "router",
                    self._route_edge,  # Funktion gibt den nächsten Node-Key zurück
                    {
                        "structure_agent": "structure_agent",
                        "writing_assistant": "writing_assistant",
                    },
                )

        self.graph.add_edge("topic_scout", "research_agent")
        self.graph.add_edge("research_agent", "structure_agent")
        self.graph.add_edge("structure_agent", "writing_assistant")
        self.graph.add_edge("writing_assistant", "reviewer_agent")
        self.graph.add_edge("reviewer_agent", END)

        self.graph.set_entry_point("router")
        self.runnable = self.graph.compile()

        # -------- Router: entscheidet Writing vs Structure --------
    def _router(self, messages: list[BaseMessage]) -> list[AIMessage]:
        
        return []

    def _route_edge(self, messages: list[BaseMessage]) -> str:
        """Gibt den Ziel-Node-Key zurück: 'writing_assistant' oder 'structure_agent'."""
        latest = messages[-1] if messages else None
        if isinstance(latest, HumanMessage):
            txt = latest.content.strip()

            # 0) Upload-Erkennung
            if re.search(r"(?i)\bupload\s*:\s*\S+", txt):
                return "writing_assistant"
            # Windows-Pfad: C:\foo\bar.md
            if re.match(r"^[A-Za-z]:\\[^:*?\"<>|\r\n]+$", txt):
                return "writing_assistant"
            # Unix/relativ: /home/..., ./file.md, .\file.md
            if re.match(r"^(?:/|\./|\.\\)[^\r\n]+$", txt):
                return "writing_assistant"

            # 1) Section/Subsection  z.B. "3.2 Model Development ..."
            lines = [l for l in txt.splitlines() if l.strip()]
            if lines:
                if re.match(r"^\s*\d+(?:\.\d+)*\s+.+", lines[0]):
                    return "writing_assistant"

            # 2) Schlüsselwörter/Style-Anweisungen
            if re.search(r"\bkeywords\s*:", txt, flags=re.IGNORECASE):
                return "writing_assistant"
            if re.search(r"\bstyle\s*:\s*(APA|MLA|Chicago)", txt, flags=re.IGNORECASE):
                return "writing_assistant"
            if re.search(r"\bstyle_guide\s*:", txt, flags=re.IGNORECASE):
                return "writing_assistant"
            if re.search(r"\blearn\s*style\s*:", txt, flags=re.IGNORECASE):
                return "writing_assistant"
            if re.match(r"^\s*show\s+style\s*$", txt, flags=re.IGNORECASE):
                return "writing_assistant"

        # Default: Outline erzeugen/aktualisieren
        return "structure_agent"

    def run(self, query: str) -> str:
            initial_message = HumanMessage(content=query)
            # gleiche Routing-Regel wie im Graph:
            next_node = self._route_edge([initial_message])
            if next_node == "writing_assistant":
                res = self.writing_assistant.chat_node([initial_message], self.research_agent)
            else:
                res = self.structure_agent.respond([initial_message], adapt=True)

            if res and hasattr(res[0], "content"):
                return res[0].content
            return str(res[0]) if res else "No response."

