# src/agents/research.py
from __future__ import annotations
from typing import List, Optional
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from src.models.models import ResearchSummary
from src.utils.local_lookup import LocalThesisLookup
from src.utils.github_lookup import GitHubLookup
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ResearchAgent:
    """
    Dummy-ResearchAgent: liefert Platzhalter + optional lokale und GitHub-Funde.
    """
    def __init__(
        self,
        local_root: Optional[str] = None,
        github_owner: Optional[str] = None,
        github_repo: Optional[str] = None,
        github_path: str = "",
        github_ref: str = "HEAD",
        github_token: Optional[str] = None,
    ):
        self.local = LocalThesisLookup(local_root) if local_root else None
        self.gh = (
            GitHubLookup(
                owner=github_owner,
                repo=github_repo,
                path=github_path,
                ref=github_ref,
                token=github_token,
            )
            if github_owner and github_repo
            else None
        )

    def fetch_updates(self, topic: str, limit: int = 5) -> List[ResearchSummary]:
        updates: List[ResearchSummary] = []

        # 1) Lokale Funde (falls konfiguriert)
        if self.local:
            try:
                local_updates = self.local.search(topic, limit=limit) or []
                logger.info(f"[ResearchAgent] {len(local_updates)} local hits for '{topic}'")
                updates.extend(local_updates)
            except Exception as e:
                logger.warning(f"[ResearchAgent] Local search failed: {e}")
                # bewusst still: Dummy soll robust bleiben
                #pass

        # 2) GitHub-Funde (falls konfiguriert)
        if self.gh and len(updates) < limit:
            try:
                remaining = max(0, limit - len(updates))
                if remaining:
                    github_updates = self.gh.search(topic, limit=remaining) or []
                    logger.info(f"[ResearchAgent] {len(github_updates)} github hits for '{topic}'")
                    updates.extend(github_updates)
            except Exception as e:
                logger.warning(f"[ResearchAgent] GitHub search failed: {e}")
                #pass

        # 3) Dummy-Eintrag anhängen (damit Adaption sichtbar bleibt)
        updates.append(
            ResearchSummary(
                title="(Dummy) Recent Study",
                authors=["Doe, J."],
                publication_year=2024,
                summary="Placeholder research summary. Replace when real research is wired in.",
                url="https://example.com",
            )
        )

        # 4) einfache Deduplizierung nach (title, url)
        seen = set()
        unique: List[ResearchSummary] = []
        for u in updates:
            key = (u.title, u.url)
            if key not in seen:
                unique.append(u)
                seen.add(key)

        # 5) begrenzen
        return unique[:limit]

    def respond(self, messages: List[BaseMessage]) -> List[AIMessage]:
        latest = messages[-1] if messages else None
        if not isinstance(latest, HumanMessage) or not latest.content.strip():
            return [AIMessage(content="Bitte gib ein Forschungsthema für die Recherche an.")]
        topic = latest.content.strip()
        updates = self.fetch_updates(topic)
        lines = [f"- {u.title} ({u.publication_year}) — {u.url}" for u in updates]
        text = f"Gefundene Forschungsarbeiten zum Thema '{topic}':\n" + "\n".join(lines)
        return [AIMessage(content=text)]
