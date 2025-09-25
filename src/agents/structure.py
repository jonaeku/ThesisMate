# src/agents/structure.py
from __future__ import annotations
from typing import List, Optional, Tuple
import re
from src.utils.logging import get_logger
from src.utils.openrouter_client import OpenRouterClient
from src.utils.storage import save_outline, outline_to_markdown_chat_compact

from src.models.models import (
    UserContext,
    AgentResponse,
    AgentInstruction,
    AgentCapabilityAssessment,
    ThesisOutline,
    OutlineChapter,
    OutlineSection,
)

logger = get_logger(__name__)

class StructureAgent:
    def __init__(self):
        self.client = OpenRouterClient()
        self.agent_name = "structure_agent"

    # ---------- Public API ----------
    def can_handle_request(self, user_input: str, context: UserContext) -> AgentCapabilityAssessment:
        """
        Spiegel des Topic-Agent-Verhaltens: schneller LLM-Check "YES/NO".
        """
        try:
            prompt = f"""You are a Structure Agent for thesis outlines.

Analyze this request and answer if it is about creating/adapting a thesis/outline/structure.

User request: "{user_input}"
Context title/topic (if any): {getattr(context, 'working_title', None) or getattr(context, 'topic', None) or 'Not set'}

You CAN handle:
- Create thesis outline/structure (chapters/sections/flow)
- Improve/adapt existing outline
- Map research notes to outline sections

You CANNOT handle:
- Writing full content
- Deep literature search
- Topic discovery from scratch

Answer ONLY "YES" or "NO" with a brief reason."""
            messages = [
                {"role": "system", "content": "Be decisive. Prefer YES if the user likely wants an outline."},
                {"role": "user", "content": prompt},
            ]
            out = self.client.chat_completion(messages, temperature=0.1, max_tokens=60)
            if out and "YES" in out.upper():
                return AgentCapabilityAssessment(
                    can_handle=True, confidence=0.9, missing_info=[], reasoning="Outline-related", suggested_questions=[]
                )
            if out and "NO" in out.upper():
                return AgentCapabilityAssessment(
                    can_handle=False, confidence=0.9, missing_info=[], reasoning=out.strip(), suggested_questions=[]
                )
            return AgentCapabilityAssessment(
                can_handle=True, confidence=0.7, missing_info=[], reasoning="Assuming outline-related", suggested_questions=[]
            )
        except Exception as e:
            logger.warning(f"can_handle_request failed: {e}")
            return AgentCapabilityAssessment(can_handle=True, confidence=0.6, missing_info=[], reasoning=str(e), suggested_questions=[])

    def process_request(
        self,
        user_input: str,
        context: UserContext,
        research_summaries: Optional[List] = None,
        options: Optional[dict] = None,
    ) -> AgentResponse:
        """
        Hauptmethode: erzeugt eine Outline (Pydantic) + gibt eine Markdown-Ansicht
        in user_message für die UI zurück. Fragt nur nach, wenn Topic/Title fehlt.
        """
        logger.info(f"StructureAgent processing: {user_input[:120]}")

        # 1) Minimalen Titel/Thema finden
        title = self._extract_title_from_input_or_context(user_input, context)

        # 2) Falls nichts Brauchbares: gezielte Rückfrage wie beim Topic-Agent
        if not title:
            question = "Für die Gliederung brauche ich einen (Arbeits-)Titel oder ein klares Thema. Wie lautet dein Thema?"
            instruction = AgentInstruction(
                requesting_agent=self.agent_name,
                action_type="ask_user",
                target="user",
                message=question,
                reasoning="Need a working title/topic to tailor the outline.",
            )
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                instructions=[instruction],
                user_message=question,
                updated_context=context,  # unverändert
            )

        # 3) Outline via LLM als Markdown erzeugen (ein Call)
        outline_md = self._generate_outline_markdown(title, research_summaries, options or {})

        # 4) Markdown -> Pydantic-Modell parsen
        thesis_outline = self._parse_outline_md_to_model(title, outline_md)

        # 5) UI-Message im gleichen Stil wie von dir erwartet (mit erkennbarem Marker)
        #    Der Prefix hilft deinem Orchestrator-Check (_is_completed_result) direkt zu enden.
        #ui_md = f"🧭 **Outline für:** *{title}*\n\n{outline_md}".strip()
        ui_md = outline_to_markdown_chat_compact(outline=self._thesis_to_outline_section(thesis_outline),topic=title)
        try:
            saved = self._save_outline(title=title, model=thesis_outline, markdown=outline_md)
            logger.info(f"[StructureAgent] Outline saved: {saved}")
        except Exception as e:
            logger.warning(f"Could not save outline: {e}")

        return AgentResponse(
            success=True,
            agent_name=self.agent_name,
            result=thesis_outline,        # Pydantic Objekt für den Orchestrator/Backend
            user_message=ui_md,           # Fertiges Markdown für die UI
            updated_context=context       # Falls du etwas im Context pflegen willst, hier (z.B. working_title)
        )

    # ---------- Helpers ----------
    def _save_outline(self, title: str, model: ThesisOutline, markdown: str):
        outline_section = self._thesis_to_outline_section(model)
        return save_outline(outline=outline_section, topic=title)

    def _extract_title_from_input_or_context(self, user_input: str, context: UserContext) -> Optional[str]:
        # a) Offensichtlich generisch? → kein Titel
        if self._is_generic_request(user_input):
            # prüfe, ob im Context schon ein echter Titel steckt
            for key in ("working_title", "topic", "title"):
                v = getattr(context, key, None)
                if v and not self._is_generic_request(v):
                    return v
            # enriched input wird unten separat geprüft
            pass

        # b) Explizit "title/topic/thema: XYZ"
        m = re.search(r'(?:title|topic|thema)\s*[:=]\s*["“]?(.+?)["”]?$', user_input, flags=re.I)
        if m:
            cand = m.group(1).strip()
            if cand and not self._is_generic_request(cand):
                return cand

        # c) Enriched input
        if "User's additional info:" in user_input:
            extra = user_input.split("User's additional info:", 1)[1].strip()
            if extra and not self._is_generic_request(extra) and len(extra) >= 4:
                return extra

        # d) Kontext
        for key in ("working_title", "topic", "title"):
            v = getattr(context, key, None)
            if v and not self._is_generic_request(v):
                return v

        # e) Strenger LLM-Fallback: generische Phrasen → "NONE"
        try:
            prompt = f"""Extract a concise, topic-specific thesis working title (<=12 words).
    If there is no real topic (e.g., generic commands like "create thesis outline/structure",
    "outline erstellt", "OUTLINE_READY"), answer EXACTLY: NONE.

    User text:
    {user_input}

    Valid title examples:
    - "AI-Assisted Triage in Emergency Departments"
    - "Federated Learning for Privacy-Preserving Medical Imaging"
    - "Bias Auditing of ICU Risk Scores Using Counterfactual Evaluation"

    Invalid (return NONE):
    - "create thesis outline"
    - "create thesis structure"
    - "outline erstellt"
    - "OUTLINE_READY"
    - "please help with outline"
    - "make an outline"
    """
            messages = [
                {"role": "system", "content": "Return only the title or NONE. Be strict."},
                {"role": "user", "content": prompt},
            ]
            out = self.client.chat_completion(messages, temperature=0.1, max_tokens=24)
            if out:
                out = out.strip().strip('"')
                if out and out.upper() != "NONE" and not self._is_generic_request(out):
                    return out
        except Exception:
            pass

        return None


    def _generate_outline_markdown(self, title: str, research_summaries: Optional[List], options: dict) -> str:
        """
        Ein LLM-Call, der NUR Markdown-Headings zurückgibt. (wie du es bereits hattest)
        """
        sys = "Return only Markdown headings (# for chapters, ## for sections). No extra prose."
        user = f"""You are an expert thesis architect. Design a rigorous, logically flowing thesis outline.

Working title/topic: "{title}"

REQUIREMENTS:
- 6–8 top-level chapters max.
- Each chapter has 2–5 subsections.
- Flow: (1) Motivation → (2) Background/Literature → (3) Method(s) → (4) Experiments/Results → (5) Discussion → (6) Conclusion/Future Work.
- CHAPTER HEADINGS MUST be specific and topic-aware, NOT generic (avoid "Introduction", "Background", "Methodology", "Discussion", "Conclusion").
- CHAPTER HEADINGS MUST be numbered as '# 1.0 <Title>', '# 2.0 <Title>', etc. Numbers must start at 1.0 and increment by 1.0.
- SECTION HEADINGS MUST be numbered as '## 1.1 <Title>', '## 1.2 <Title>', ...; numbering resets per chapter.
- Be specific in subsection names (avoid 'misc' or generic names).
- Return ONLY headings, nothing else.

FORMAT EXAMPLE (shape only):
# 1.0 <Topic-Specific Motivation & Problem Statement>
## 1.1 <Concrete Pain Points in {title}>
## 1.2 <Objectives and Research Questions>
# 2.0 <Topic-Specific Background & Related Work>
## 2.1 <Key Concepts and Taxonomies in {title}>
## 2.2 <State of the Art in {title}>
# 3.0 <Methods Tailored to {title}>
## 3.1 <Data Sources and Preprocessing in {title}>
## 3.2 <Modeling Approach for {title}>
(...continue...)"""
        messages = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
        md = self.client.chat_completion(messages, temperature=0.5, max_tokens=1600)
        return md.strip()

    def _parse_outline_md_to_model(self, title: str, md: str) -> ThesisOutline:
        """
        Sehr toleranter Parser für das simple # / ## Schema.
        """
        chapters: List[OutlineChapter] = []
        current: Optional[OutlineChapter] = None

        for line in md.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("# "):  # Kapitel
                if current:
                    chapters.append(current)
                chap_title = s[2:].strip()
                current = OutlineChapter(title=chap_title, sections=[])
            elif s.startswith("## "):  # Abschnitt
                if not current:
                    # Falls der LLM mit ## startet, lege ein Dummy-Kapitel an
                    current = OutlineChapter(title="Chapter 1", sections=[])
                sec_title = s[3:].strip()
                # Optionale Nummer entkoppeln (1.1 foo -> foo)
                sec_title = re.sub(r'^\d+(\.\d+)*\s*', '', sec_title).strip()
                current.sections.append(OutlineSection(title=sec_title))
            # alles andere ignorieren (keine Fließtexte erwartet)

        if current:
            chapters.append(current)

        return ThesisOutline(title=title, chapters=chapters)
    
    def _thesis_to_outline_section(self, thesis: ThesisOutline) -> OutlineSection:
        return OutlineSection(
            title=thesis.title,
            subsections=[
                OutlineSection(
                    title=ch.title,
                    subsections=[OutlineSection(title=s.title, subsections=[]) for s in (ch.sections or [])]
                )
                for ch in (thesis.chapters or [])
            ]
        )
    
    def _is_generic_request(self, text: str) -> bool:
        if not text:
            return True
        t = text.strip().lower()

        generic_patterns = [
            r"^\s*create (a )?(thesis )?(outline|structure)\s*$",
            r"^\s*make (an )?(outline|structure)\s*$",
            r"^\s*generate (an )?(outline|structure)\s*$",
            r"^\s*thesis (outline|structure)\s*$",
            r"^\s*outline\s*$",
            r"^\s*structure\s*$",
            r"^\s*outline erstellt\.?\s*$",
            r"^\s*outline_ready\s*$",
            r"^\s*please help( me)? (with )?(an )?(outline|structure)\s*$",
            r".*\bhilfe\b.*\b(gliederung|outline|struktur)\b.*",
        ]
        return any(re.search(p, t) for p in generic_patterns)
