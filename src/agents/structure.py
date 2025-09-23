from __future__ import annotations
from typing import List, Dict, Optional
import json
import re
import os

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from src.models.models import OutlineSection, ResearchSummary
from src.utils.gemini_client import GeminiClient

from src.utils.logging import get_logger
from src.utils.openrouter_client import OpenRouterClient

logger = get_logger(__name__)

CHAPTERS: Dict[str, Dict[str, str]] = {
    "Introduction":       {"num": 1, "desc": "Introduce the topic, problem, objectives, and significance."},
    "Literature Review":  {"num": 2, "desc": "Synthesize prior work and theoretical foundations."},
    "Methodology":        {"num": 3, "desc": "Design, data, and analysis plan."},
    "Results":            {"num": 4, "desc": "Report empirical or analytical findings."},
    "Discussion":         {"num": 5, "desc": "Interpretation, implications, limitations."},
    "Conclusion":         {"num": 6, "desc": "Summary, conclusions, and future work."},
}

class StructureAgent:
    def __init__(self, research_agent: Optional[object] = None, save_path: str = "./thesis/my_thesis.md"):
        self.client = GeminiClient(model="gemini-1.5-flash")
     #   self.client = OpenRouterClient()
        self.research_agent = research_agent
        self.save_path = save_path

    def respond(self, messages: List[BaseMessage], adapt: bool = False) -> List[AIMessage]:
        latest = messages[-1] if messages else None
        if not isinstance(latest, HumanMessage) or not latest.content.strip():
            return [AIMessage(content="Bitte gib ein Forschungsthema an.")]
        topic = " ".join(latest.content.split())[:500]

        chapter_sections: List[OutlineSection] = []
        for chapter_name, meta in CHAPTERS.items():
            subs = self._generate_chapter_subsections(topic, chapter_name, meta["num"])
            chapter_sections.append(
                OutlineSection(
                    title=f'{meta["num"]}. {chapter_name}',
                    description=meta["desc"],
                    subsections=subs,
                )
            )

        outline = OutlineSection(
            title=f"Thesis Outline: {topic}",
            description=f"Thesis structure for {topic}",
            subsections=chapter_sections,
        )

        if adapt and self.research_agent is not None:
            updates = self.research_agent.fetch_updates(topic)
            outline = self._adapt_outline_with_research(outline, updates)
        
        content = self._format_outline(outline)

        self._save_outline_to_file(content)

        return [AIMessage(content=content)]

    # ---------- helper ----------
    def _save_outline_to_file(self, text: str) -> None:
            os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
            with open(self.save_path, "w", encoding="utf-8") as f:
                f.write(text)

    def _adapt_outline_with_research(self, outline: OutlineSection, updates: List[ResearchSummary]) -> OutlineSection:
        if not updates:
            return outline

        # next chapter
        lit = next((s for s in outline.subsections if s.title.startswith("2. ")), None)
        if not lit:
            return outline

        # source
        def _src_label(u: ResearchSummary) -> str:
            url = (u.url or "").lower()
            if url.startswith("http") and "github.com" in url:
                return "GitHub"
            if ":\\" in url or url.startswith("/") or url.startswith(".\\") or url.startswith("./"):
                return "Local"
            # Fallback über authors
            if u.authors and any(a.lower().startswith("github") for a in u.authors):
                return "GitHub"
            if u.authors and any(a.lower().startswith("local") for a in u.authors):
                return "Local"
            return "Unknown"

        # markdown labels
        lines = []
        for u in updates:
            label = _src_label(u)
            if u.url:
                lines.append(f"- **{u.title}** ({label}) — {u.url}")
            else:
                lines.append(f"- **{u.title}** ({label})")

        idx = len(lit.subsections) + 1
        lit.subsections.append(
            OutlineSection(
                title=f"2.{idx} Recent Research Updates (Auto)",
                description="Auto-integrated recent research updates.\n\n" + "\n".join(lines),
            )
        )
        return outline


    def _generate_chapter_subsections(self, topic: str, chapter_name: str, chapter_num: int) -> List[OutlineSection]:
        prompt = (
            f'Create 4–6 specific subsections for the chapter "{chapter_name}" '
            f'of a thesis on "{topic}". Each array item must be an object with exactly:\n'
            f'- "title": short, topic-specific title (no numbering)\n'
            f'- "description": 1–2 sentences\n\n'
            f"Return ONLY a JSON array, no prose, no code fences, no comments."
        )
        messages = [
            {"role": "system", "content": "You are a JSON API. You ONLY return JSON arrays."},
            {"role": "user", "content": prompt},
        ]

        raw = self.client.chat_completion(messages, temperature=0.0, max_tokens=300)
        data = json.loads(raw.strip())  # strikt

        if not isinstance(data, list) or not (4 <= len(data) <= 6):
            raise ValueError(f"{chapter_name}: expected 4–6 items.")

        out: List[OutlineSection] = []
        for i, item in enumerate(data, 1):
            if not isinstance(item, dict) or "title" not in item or "description" not in item:
                raise ValueError(f"{chapter_name}: each item needs 'title' and 'description'.")
            title = re.sub(r"^\d+(\.\d+)*\s*", "", str(item["title"]).strip())
            out.append(OutlineSection(title=f"{chapter_num}.{i} {title}", description=str(item["description"]).strip()))
        return out

    def _format_outline(self, outline: OutlineSection) -> str:
        def fmt(sec: OutlineSection, level: int = 0) -> str:
            indent = "  " * level
            s = f"{indent}**{sec.title}**\n{indent}{sec.description}\n\n"
            for sub in sec.subsections:
                s += fmt(sub, level + 1)
            return s

        body = "".join(fmt(s) for s in outline.subsections)
        return f"# {outline.title}\n\n{outline.description}\n\n{body}"



