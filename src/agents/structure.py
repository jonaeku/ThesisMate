# src/agents/structure.py
from __future__ import annotations
from typing import List, Optional
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
        Mirror of Topic-Agent behavior: quick LLM-based "YES/NO" capability check.
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
            return AgentCapabilityAssessment(
                can_handle=True, confidence=0.6, missing_info=[], reasoning=str(e), suggested_questions=[]
            )

    def process_request(
        self,
        user_input: str,
        context: UserContext,
        research_summaries: Optional[List] = None,
        options: Optional[dict] = None,
    ) -> AgentResponse:
        logger.info(f"[StructureAgent] processing: {user_input[:120]}")
        try:
            # 1) Enrich context
            updated_ctx = self._update_context_from_input(user_input, context)

            # 2) Capability check
            assessment = self.can_handle_request(user_input, updated_ctx)
            if not assessment.can_handle:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    capability_assessment=assessment,
                    user_message=f"I can't help with this request. {assessment.reasoning}",
                    updated_context=updated_ctx,
                )

            # 3) Do we have enough info?
            if not self._has_enough_info(updated_ctx):
                question = self._get_next_question(updated_ctx)
                instruction = AgentInstruction(
                    requesting_agent=self.agent_name,
                    action_type="ask_user",
                    target="user",
                    message=question,
                    reasoning="Need this information to create a suitable outline.",
                )
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    instructions=[instruction],
                    user_message=question,
                    updated_context=updated_ctx,
                )

            # 4) Generate outline (Markdown)
            title = updated_ctx.working_title
            if not title:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    user_message="What is your working title or precise topic?",
                    updated_context=updated_ctx,
                )
            outline_md = self._generate_outline_markdown(
                title=title,
                research_summaries=research_summaries,
                options=options or {},
                context=updated_ctx,
            )

            # 5) Parse Markdown → model
            thesis_outline = self._parse_outline_md_to_model(title, outline_md)

            # 6) (Optional) validate with research tool
            # if getattr(self, "research_tool", None):
            #     thesis_outline = self._validate_outline_with_research(thesis_outline)

            # 7) UI formatting
            ui_md = outline_to_markdown_chat_compact(
                outline=self._thesis_to_outline_section(thesis_outline),
                topic=title
            )

            try:
                self._save_outline(title=title, model=thesis_outline, markdown=outline_md)
            except Exception as e:
                logger.warning(f"[StructureAgent] Could not save outline: {e}")

            return AgentResponse(
                success=True,
                agent_name=self.agent_name,
                result=thesis_outline,
                user_message=ui_md,
                updated_context=updated_ctx,
            )
        except Exception as e:
            logger.error(f"[StructureAgent] Error: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                user_message=f"An error occurred: {e}",
                updated_context=context,
            )

    # ---------- Helpers: context & gating ----------

    def _update_context_from_input(self, user_input: str, context: UserContext) -> UserContext:
        """
        Set working_title only when it is clearly identifiable:
        - Explicit field: "Title/Topic: <...>"
        - Command phrases like "create outline for <TITLE>"
        - Orchestrator format: "User's additional info: <TITLE>"
        No generic fallback.
        """
        if getattr(context, "working_title", None):
            return context  # already set

        text = (user_input or "").strip()

        # 1) Explicit: "Title/Topic: ..."
        m = re.search(r'(?:titel|thema|topic|title)\s*[:=]\s*["“]?(.+?)["”]?\s*$', text, flags=re.I | re.M)
        if m:
            cand = m.group(1).strip()
            if cand and not self._is_generic_request(cand):
                context.working_title = cand
                logger.info(f"[StructureAgent] title from explicit field: {context.working_title!r}")
                return context

        # 2) Orchestrator format: "User's additional info: <TITLE>" (multi-line)
        m = re.search(r"User['’]s additional info\s*:\s*(.+)$", text, flags=re.I | re.M)
        if m:
            cand = m.group(1).strip().strip('"\u201C\u201D')  # trim quotes/„“
            if cand and not self._is_generic_request(cand):
                context.working_title = cand
                logger.info(f"[StructureAgent] title from orchestrator additional info: {context.working_title!r}")
                return context

        # 3) Command phrases e.g. "create outline for <TITLE>" / "gliederung für <TITEL>"
        cmd_title = self._extract_title_from_command_phrase(text) if hasattr(self, "_extract_title_from_command_phrase") else None
        if cmd_title:
            context.working_title = cmd_title
            logger.info(f"[StructureAgent] title from command phrase: {context.working_title!r}")
            return context

        # No generic fallback
        return context

    def _has_enough_info(self, ctx: UserContext) -> bool:
        """
        Minimal requirement: a working title must be present.
        """
        return bool(getattr(ctx, "working_title", None))

    def _get_next_question(self, ctx: UserContext) -> str:
        """
        Ask specifically for the title/topic when missing.
        """
        if not getattr(ctx, "working_title", None):
            return "What is your working title or precise topic?"
        return ""  # nothing to ask

    def _is_generic_request(self, text: str) -> bool:
        """
        Detects generic outline requests (EN/DE), including short questions like
        "can you create a thesis outline?" to avoid treating them as titles.
        """
        if not text:
            return True
        t = text.strip().lower()

        generic_patterns = [
            r"^\s*(can|could|would|will|please|pls)\s+(you\s+)?(create|make|generate|produce|build|write|prepare|design)\s+(a|an|the)?\s*(thesis\s+)?(outline|structure)s?\s*\??\s*$",
            r"^\s*(create|make|generate|produce|build|write|prepare|design)\s+(a|an|the)?\s*(thesis\s+)?(outline|structure)s?\s*\??\s*$",
            r"^\s*(please\s+)?help( me)?\s+(with\s+)?(an|a|the)?\s*(thesis\s+)?(outline|structure)\s*\??\s*$",
            r"^\s*(kannst du|könntest du|würdest du|bitte)\s+(eine?n?\s+)?(thesis\s+)?(gliederung|struktur|disposition|outline)\s+(erstellen|machen|generieren|bauen|schreiben)\s*\??\s*$",
            r"^\s*(erstelle|erstellen sie|mach|mache|generiere|baue|schreibe)\s+(eine?n?\s+)?(thesis\s+)?(gliederung|struktur|disposition|outline)\s*\??\s*$",
            r"^\s*(hilfe|bitte)\s+.*\b(gliederung|struktur|disposition|outline)\b.*$",
            r"^\s*(thesis\s+)?(outline|structure|gliederung|struktur|disposition)\s*\??\s*$",
            r"^\s*outline\s*\??\s*$",
            r"^\s*structure\s*\??\s*$",
            r"^\s*outline_ready\s*$",
            r"^\s*outline erstellt\.?\s*$",
        ]
        if any(re.search(p, t) for p in generic_patterns):
            return True

        # Short question with "outline/gliederung/struktur/disposition" → generic
        if ("outline" in t or "gliederung" in t or "struktur" in t or "disposition" in t) and t.endswith("?") and len(t) <= 60:
            return True

        return False

    def _extract_title_from_command_phrase(self, text: str) -> Optional[str]:
        """
        Extract the title from command phrases like 'create outline for "<TITLE>"'.
        Covers EN + DE variants. Returns None if no title can be detected.
        """
        if not text:
            return None
        t = text.strip()

        patterns = [
            # EN: "create/make/generate ... outline for <title>"
            r'^\s*(?:please\s+)?(?:can|could|would|will)?\s*(?:you\s+)?'
            r'(?:create|make|generate|write|prepare|design|build)\s+'
            r'(?:an?\s+)?(?:thesis\s+)?(?:outline|structure)\s*'
            r'(?:for|on|about)\s*[:\-]?\s*[\"“]?(.+?)[\"”]?\s*$',

            # EN: "create outline: <title>" or "create outline <title>"
            r'^\s*(?:create|make|generate|write|prepare|design|build)\s+'
            r'(?:an?\s+)?(?:thesis\s+)?(?:outline|structure)\s*[:\-]?\s*[\"“]?(.+?)[\"”]?\s*$',

            # EN short: "outline for <title>"
            r'^\s*(?:outline|structure)\s*(?:for|on|about)\s*[:\-]?\s*[\"“]?(.+?)[\"”]?\s*$',

            # DE: "erstelle/erstellen sie/generiere ... gliederung/struktur für <title>"
            r'^\s*(?:erstelle|erstellen sie|generiere|mach|mache|baue|schreibe)\s+'
            r'(?:eine?n?\s+)?(?:gliederung|struktur|outline|disposition)\s*'
            r'(?:für|zu|über)\s*[:\-]?\s*[\"“]?(.+?)[\"”]?\s*$',

            # DE short: "gliederung für <title>"
            r'^\s*(?:gliederung|struktur|outline|disposition)\s*'
            r'(?:für|zu|über)\s*[:\-]?\s*[\"“]?(.+?)[\"”]?\s*$',
        ]

        for p in patterns:
            m = re.match(p, t, flags=re.IGNORECASE)
            if m:
                cand = m.group(1).strip().strip('"\''"“”")
                # Clean minor boilerplate like leading "for:"/"für:"
                cand = re.sub(r'^\s*(for|für|zu|about|on)\s*[:\-]\s*', '', cand, flags=re.I).strip()
                if cand and not self._is_generic_request(cand):
                    return cand
        return None

    # ---------- Helpers: generation, parsing, persistence ----------

    def _generate_outline_markdown(
        self,
        title: str,
        research_summaries: Optional[List],
        options: dict,
        context: Optional[UserContext] = None
    ) -> str:
        """
        Single LLM call that returns ONLY Markdown headings.
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
        Tolerant parser for a simple # / ## heading schema.
        """
        chapters: List[OutlineChapter] = []
        current: Optional[OutlineChapter] = None

        for line in md.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("# "):  # chapter
                if current:
                    chapters.append(current)
                chap_title = s[2:].strip()
                current = OutlineChapter(title=chap_title, sections=[])
            elif s.startswith("## "):  # section
                if not current:
                    # If markdown starts with a section, create a dummy chapter
                    current = OutlineChapter(title="Chapter 1", sections=[])
                sec_title = s[3:].strip()
                # Detach optional numbering (e.g., "1.1 foo" -> "foo")
                sec_title = re.sub(r'^\d+(\.\d+)*\s*', '', sec_title).strip()
                current.sections.append(OutlineSection(title=sec_title))
            # ignore everything else (no body text expected)

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

    def _save_outline(self, title: str, model: ThesisOutline, markdown: str):
        outline_section = self._thesis_to_outline_section(model)
        return save_outline(outline=outline_section, topic=title)
