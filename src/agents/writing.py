from __future__ import annotations
from typing import List, Dict, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from pathlib import Path
import re

from src.models.models import ResearchSummary
from src.utils.openrouter_client import OpenRouterClient
from src.utils.gemini_client import GeminiClient
from src.utils.writing_agent.style import load_style, save_style, handle_style_command
from src.utils.writing_agent.guardrails import is_upload_command, validate_upload, ingest_guardrail_file, compose_guardrails_text
from src.utils.writing_agent.writing_input import parse_writing_input, scan_style_command
from src.utils.writing_agent.citations import combined_cites
from src.utils.writing_agent.thesis_io import save_paragraph_to_file

DEFAULT_GUIDE = ("Academic, concise, precise terminology, formal tone, "
                 "active voice where appropriate, hedging when evidence is limited.")

class WritingAssistantAgent:
    def __init__(self, citation_style: str = "APA", temperature: float = 0.3):
        self.client = GeminiClient(model="gemini-1.5-flash")
        #self.client = OpenRouterClient()
        self.temperature = temperature
        self.style_guide, self.citation_style = load_style(DEFAULT_GUIDE, citation_style)

    # — style setters —
    def set_citation_style(self, style: str) -> None:
        self.citation_style = style
        save_style(self.style_guide, self.citation_style)

    def set_style_guide(self, guide: str) -> None:
        self.style_guide = guide.strip()
        save_style(self.style_guide, self.citation_style)

    def learn_style_from_sample(self, sample_text: str) -> None:
        self.style_guide = f"Mirror this style: {sample_text.strip()}"
        save_style(self.style_guide, self.citation_style)

    # — node —
    def chat_node(self, messages: List[BaseMessage], research_agent, save_path: Path = Path("./thesis/my_thesis.md")) -> List[AIMessage]:
        latest = messages[-1] if messages else None
        if not isinstance(latest, HumanMessage) or not latest.content.strip():
            return [AIMessage(content="Bitte Section und danach Paragraph oder 'keywords:' senden.")]

        txt = latest.content.strip()

       # Style
        res = handle_style_command(self, txt)
        if res:
            return [res]

        st = scan_style_command(messages)
        if st: self.set_citation_style(st)

        # Upload
        path_str = is_upload_command(latest.content)
        if path_str:
            p = validate_upload(path_str)
            dst = ingest_guardrail_file(p)
            return [AIMessage(content=f"Guardrail gespeichert: {dst.name}")]

       
        # - input -
        section_title, paragraph, keywords = parse_writing_input(latest.content)
        if not section_title: return [AIMessage(content="Section-Zeile fehlt.")]
        if not paragraph and not keywords: return [AIMessage(content="Bitte Paragraph oder 'keywords:' angeben.")]

        summaries: List[ResearchSummary] = research_agent.fetch_updates(section_title, limit=3)
        draft = self.respond({"title": section_title, "description": ""}, summaries, paragraph, keywords)
        save_paragraph_to_file(section_title, draft, save_path)
        return [AIMessage(content=draft)]


    def respond(self, section: Dict, research_summaries: List[ResearchSummary],
                user_paragraph: Optional[str] = None, keywords: Optional[List[str]] = None) -> str:
        title = section.get("title", "Section")
        cites_text = combined_cites(research_summaries, self.citation_style)
        user_block = f"USER_PARAGRAPH:\n{user_paragraph.strip()}" if (user_paragraph and user_paragraph.strip()) \
                     else f"KEYWORDS:\n{'; '.join(k.strip() for k in (keywords or []))}"
        task = "Rewrite the paragraph into rigorous academic prose while preserving meaning." \
               if (user_paragraph and user_paragraph.strip()) else \
               "Compose a concise academic paragraph that faithfully reflects the provided keywords (no speculation)."

        guardrails_block = compose_guardrails_text()
        guardrails_line = f"GUARDRAILS:\n{guardrails_block}\n" if guardrails_block else ""

        prompt = (
            f"You are an academic writing assistant.\n"
            f"SECTION TITLE: {title}\n"
            f"STYLE GUIDE: {self.style_guide}\n"
            f"{guardrails_line}"
            f"CITATION STYLE: {self.citation_style}\n"
            f"TASK: {task}\n"
            f"CONSTRAINTS:\n"
            f"- One tight paragraph (~120–170 words).\n"
            f"- Maintain factual consistency with the input only.\n"
            f"- Insert inline citations where appropriate: {cites_text if cites_text else '(no citations if not relevant)'}\n"
            f"- Do not invent references.\n"
            f"- No bullet lists; continuous prose.\n\n"
            f"{user_block}\n"
        )
        messages = [
            {"role": "system", "content": "You transform text into consistent academic prose with specified citation style."},
            {"role": "user", "content": prompt},
        ]
        return self.client.chat_completion(messages, temperature=self.temperature, max_tokens=450).strip()
