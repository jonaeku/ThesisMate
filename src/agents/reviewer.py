from __future__ import annotations
import os, re, glob, json, hashlib
from typing import Optional, Tuple, List
from src.utils.logging import get_logger
from src.utils.openrouter_client import OpenRouterClient

# storage + models used elsewhere in your project
from src.utils.storage import (
    load_latest_outline, _strip_leading_enumeration, list_guardrail_files
)
from src.models.models import (
    UserContext,
    AgentResponse, AgentInstruction, AgentCapabilityAssessment,
    ThesisOutline, OutlineSection, OutlineChapter, WritingStyleConfig, GuardrailsConfig
)

# global style store (style.json in data/thesis/config)
from src.utils.style_store import get_style as get_global_style


logger = get_logger(__name__)

# IMPORTANT: matches your real layout like
# data/thesis/chapter/04_experimental-design-and-results-for-ai-in-healthcare/08.03.md
CHAPTERS_ROOT = "data/thesis/chapter"
SECTION_GLOB  = os.path.join(CHAPTERS_ROOT, "**", "*.md")


class ReviewerAgent:
    def __init__(self):
        self.client = OpenRouterClient()
        self.agent_name = "reviewer_agent"
        self._guardrails_cache: dict | None = None

    # ---------- CAPABILITY ----------
    def can_handle_request(self, user_input: str, context: UserContext) -> AgentCapabilityAssessment:
        """
        Decide if this is a review task.
        Triggers on: 'review', 'feedback' (also supports German variants: 'kritik', 'bewerte', 'überarbeiten').
        """
        t = (user_input or "").lower()
        if re.search(r"\b(review|feedback|kritik|bewerte|überarbeit|ueberarbeit)\b", t):
            return AgentCapabilityAssessment(can_handle=True, confidence=0.9, missing_info=[], reasoning="Review intent detected", suggested_questions=[])
        # be generous but safe
        return AgentCapabilityAssessment(can_handle=False, confidence=0.4, missing_info=[], reasoning="No explicit review intent", suggested_questions=[])

    # ---------- MAIN ----------
    def process_request_old(self, user_input: str, context: UserContext, options: Optional[dict] = None) -> AgentResponse:
        """
        Topic-Agent-style pipeline:
        1) Enrich context
        2) can_handle_request (if present)
        3) Gate: do we have enough info? → ask targeted question
        4) Perform review (inline / chapter / all)
        5) Format & return

        Modes:
        - "review: <text>"     → Inline review of the provided text
        - "review chapter 2.3" → Review a saved section
        - "review all"         → Short pass over multiple saved sections
        """
        logger.info(f"[ReviewerAgent] processing: {user_input[:160]}")
        options = options or {}
        t = (user_input or "").strip()

        try:
            # ---------------- 1) Enrich context ----------------
            updated_ctx = self._update_context_from_input_basic(user_input, context) if hasattr(self, "_update_context_from_input_basic") else context
            outline = getattr(updated_ctx, "latest_outline", None)

            # ---------------- 2) Capability check ---------------
            assessment = None
            if hasattr(self, "can_handle_request"):
                try:
                    assessment = self.can_handle_request(user_input, updated_ctx)
                except Exception as e:
                    logger.warning(f"[ReviewerAgent] can_handle_request failed, assuming YES: {e}")
            if assessment and not assessment.can_handle:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    capability_assessment=assessment,
                    user_message=f"I can't help with this. {assessment.reasoning}",
                    updated_context=updated_ctx,
                )

            # ---------------- 3) Gate: enough info? --------------
            # Detect mode (without heavy file IO)
            inline_match = re.search(r"\breview\s*:\s*(.+)$", t, flags=re.I | re.S)
            wants_all   = bool(re.search(r"\breview\s+all\b", t, flags=re.I))
            target_pair = None if (inline_match or wants_all) else self._parse_chapter_target(t)

            # If nothing recognized → ask targeted question (Topic-Agent style)
            if not inline_match and not wants_all and not target_pair:
                menu = self._format_outline_for_prompt(outline) if outline else ""
                help_msg = (
                    "What should I review?\n"
                    "- `review: <Your text>`\n"
                    "- `review chapter 2.3` (or `review kapitel 2.3`)\n"
                    "- `review all`\n"
                ) + (("\nCurrent outline:\n" + menu) if menu else "")
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    instructions=[AgentInstruction(
                        requesting_agent=self.agent_name,
                        action_type="ask_user",
                        target="user",
                        message=help_msg,
                        reasoning="Need explicit review scope."
                    )],
                    user_message=help_msg,
                    updated_context=updated_ctx
                )

            # ---------------- 4) Perform review -------------------
            # 4.1 Load style/guardrails and prompt helpers only now (when needed)
            style_json = get_global_style() or {}
            style_guide_text = style_json.get("style_guide", "")
            citation_style   = style_json.get("citation_style", "APA")
            guardrail_text   = self._read_guardrail_docs(max_chars=6000)

            # Mode A: Inline review
            if inline_match:
                passage = inline_match.group(1).strip()
                if not passage:
                    msg = "Please append the text to be reviewed after `review:`."
                    return AgentResponse(
                        success=False, agent_name=self.agent_name,
                        instructions=[AgentInstruction(
                            requesting_agent=self.agent_name, action_type="ask_user",
                            target="user", message=msg, reasoning="Inline passage missing."
                        )],
                        user_message=msg, updated_context=updated_ctx
                    )
                critique = self._review_with_llm(passage, style_guide_text, citation_style, guardrail_text)
                return AgentResponse(
                    success=True, agent_name=self.agent_name,
                    user_message=f"🧪 **Review (inline passage)**\n\n{critique}",
                    updated_context=updated_ctx
                )

            # Mode B: Review ALL
            if wants_all:
                found = self._find_all_sections()
                if not found:
                    msg = "I couldn't find any saved sections. Alternatively, send `review: <Text>` for an inline review."
                    return AgentResponse(
                        success=False, agent_name=self.agent_name,
                        instructions=[AgentInstruction(
                            requesting_agent=self.agent_name, action_type="ask_user",
                            target="user", message=msg, reasoning="No saved sections available."
                        )],
                        user_message=msg, updated_context=updated_ctx
                    )

                # Compact batch (limit prompt size)
                import os
                snippets = []
                for path in found[:12]:
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            txt = f.read().strip()
                        if len(txt) > 1800:
                            txt = txt[:1800] + "\n… (truncated)"
                        snippets.append(f"\n---\n# {os.path.basename(path)}\n{txt}")
                    except Exception:
                        continue
                batch = "\n".join(snippets)
                critique = self._review_with_llm(batch, style_guide_text, citation_style, guardrail_text, multi_section=True)
                return AgentResponse(
                    success=True, agent_name=self.agent_name,
                    user_message=f"🧵 **Overall Review (excerpt, up to 12 sections)**\n\n{critique}",
                    updated_context=updated_ctx
                )

            # Mode C: Review a specific chapter/section (e.g., 2.3)
            if target_pair:
                ch_idx, sec_idx = target_pair

                # Ensure an outline is present (for nicer titles)
                if not outline:
                    sec = load_latest_outline()
                    if sec:
                        outline = self._section_to_thesis_outline(sec)
                        updated_ctx.latest_outline = outline

                md, err = self._load_markdown_for_review(ch_idx, sec_idx)
                if err:
                    msg = f"⚠️ {err}\n(Tip: the section file may be named e.g., `08.03.md`, `8.3.md`, or `8-3.md`.)"
                    return AgentResponse(
                        success=False, agent_name=self.agent_name,
                        instructions=[AgentInstruction(
                            requesting_agent=self.agent_name, action_type="ask_user", target="user",
                            message=msg, reasoning="No saved section markdown found."
                        )],
                        user_message=msg, updated_context=updated_ctx
                    )

                critique = self._review_with_llm(md, style_guide_text, citation_style, guardrail_text)
                title = self._title_for(outline, ch_idx, sec_idx) if outline else f"Chapter {ch_idx}.{sec_idx or 0}".rstrip(".0")
                return AgentResponse(
                    success=True, agent_name=self.agent_name,
                    user_message=f"🔎 **Review for {title}**\n\n{critique}",
                    updated_context=updated_ctx
                )

            # Fallback (should not be reached)
            msg = "I couldn't determine the review mode. Send `review: <Text>` or `review chapter 2.3`."
            return AgentResponse(
                success=False, agent_name=self.agent_name,
                instructions=[AgentInstruction(
                    requesting_agent=self.agent_name, action_type="ask_user", target="user",
                    message=msg, reasoning="Ambiguous review request."
                )],
                user_message=msg, updated_context=updated_ctx
            )

        except Exception as e:
            logger.error(f"[ReviewerAgent] Error: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                user_message=f"An error occurred: {e}",
                updated_context=context
            )

    def process_request(self, user_input: str, context: UserContext, options: Optional[dict] = None) -> AgentResponse:
        """
        Topic-Agent-style pipeline:
        1) Enrich context
        2) Capability check (if present)
        3) Gate: do we have enough info? → ask targeted question
        4) Perform review (inline / chapter / all)
        5) Format & return

        Modes:
        - "review: <text>"     → Inline review of the provided text
        - "review chapter 2.3" → Review a saved section
        - "review all"         → Short pass over multiple saved sections
        """
        logger.info(f"[ReviewerAgent] processing: {user_input[:160]}")
        options = options or {}
        t = (user_input or "").strip()

        try:
            # ---------------- 1) Enrich context ----------------
            updated_ctx = self._update_context_from_input_basic(user_input, context) if hasattr(self, "_update_context_from_input_basic") else context
            outline = getattr(updated_ctx, "latest_outline", None)

            # ---------------- 2) Capability check ---------------
            assessment = None
            if hasattr(self, "can_handle_request"):
                try:
                    assessment = self.can_handle_request(user_input, updated_ctx)
                except Exception as e:
                    logger.warning(f"[ReviewerAgent] can_handle_request failed, assuming YES: {e}")
            if assessment and not assessment.can_handle:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    capability_assessment=assessment,
                    user_message=f"I can't help with this. {assessment.reasoning}",
                    updated_context=updated_ctx,
                )

            # ---------------- 3) Gate: enough info? --------------
            # Lightweight intent detection only (no heavy IO)
            inline_match = re.search(r"\breview\s*:\s*(.+)$", t, flags=re.I | re.S)
            wants_all   = bool(re.search(r"\breview\s+all\b", t, flags=re.I))
            target_pair = None if (inline_match or wants_all) else self._parse_chapter_target(t)

            ok, _missing = self._has_enough_info_review(inline_match=inline_match, wants_all=wants_all, target_pair=target_pair)
            if not ok:
                question = self._get_next_question_review(updated_ctx, outline=outline)
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    instructions=[AgentInstruction(
                        requesting_agent=self.agent_name,
                        action_type="ask_user",
                        target="user",
                        message=question,
                        reasoning="Need this information to perform the review."
                    )],
                    user_message=question,
                    updated_context=updated_ctx
                )

            # ---------------- 4) Perform review -------------------
            # 4.1 Load style/guardrails and prompt helpers only now (when needed)
            style_json = get_global_style() or {}
            style_guide_text = style_json.get("style_guide", "")
            citation_style   = style_json.get("citation_style", "APA")
            guardrail_text   = self._read_guardrail_docs(max_chars=6000)

            # Mode A: Inline review
            if inline_match:
                passage = inline_match.group(1).strip()
                if not passage:
                    msg = "Please append the text to be reviewed after `review:`."
                    return AgentResponse(
                        success=False, agent_name=self.agent_name,
                        instructions=[AgentInstruction(
                            requesting_agent=self.agent_name, action_type="ask_user",
                            target="user", message=msg, reasoning="Inline passage missing."
                        )],
                        user_message=msg, updated_context=updated_ctx
                    )
                critique = self._review_with_llm(passage, style_guide_text, citation_style, guardrail_text)
                return AgentResponse(
                    success=True, agent_name=self.agent_name,
                    user_message=f"🧪 **Review (inline passage)**\n\n{critique}",
                    updated_context=updated_ctx
                )

            # Mode B: Review ALL
            if wants_all:
                found = self._find_all_sections()
                if not found:
                    msg = "I couldn't find any saved sections. Alternatively, send `review: <Text>` for an inline review."
                    return AgentResponse(
                        success=False, agent_name=self.agent_name,
                        instructions=[AgentInstruction(
                            requesting_agent=self.agent_name, action_type="ask_user",
                            target="user", message=msg, reasoning="No saved sections available."
                        )],
                        user_message=msg, updated_context=updated_ctx
                    )

                # Compact batch (limit prompt size)
                import os
                snippets = []
                for path in found[:12]:
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            txt = f.read().strip()
                        if len(txt) > 1800:
                            txt = txt[:1800] + "\n… (truncated)"
                        snippets.append(f"\n---\n# {os.path.basename(path)}\n{txt}")
                    except Exception:
                        continue
                batch = "\n".join(snippets)
                critique = self._review_with_llm(batch, style_guide_text, citation_style, guardrail_text, multi_section=True)
                return AgentResponse(
                    success=True, agent_name=self.agent_name,
                    user_message=f"🧵 **Overall Review (excerpt, up to 12 sections)**\n\n{critique}",
                    updated_context=updated_ctx
                )

            # Mode C: Review a specific chapter/section (e.g., 2.3)
            if target_pair:
                ch_idx, sec_idx = target_pair

                # Ensure an outline is present (for nicer titles)
                if not outline:
                    sec = load_latest_outline()
                    if sec:
                        outline = self._section_to_thesis_outline(sec)
                        updated_ctx.latest_outline = outline

                md, err = self._load_markdown_for_review(ch_idx, sec_idx)
                if err:
                    msg = f"⚠️ {err}\n(Tip: the section file may be named e.g., `08.03.md`, `8.3.md`, or `8-3.md`.)"
                    return AgentResponse(
                        success=False, agent_name=self.agent_name,
                        instructions=[AgentInstruction(
                            requesting_agent=self.agent_name, action_type="ask_user", target="user",
                            message=msg, reasoning="No saved section markdown found."
                        )],
                        user_message=msg, updated_context=updated_ctx
                    )

                critique = self._review_with_llm(md, style_guide_text, citation_style, guardrail_text)
                title = self._title_for(outline, ch_idx, sec_idx) if outline else f"Chapter {ch_idx}.{sec_idx or 0}".rstrip(".0")
                return AgentResponse(
                    success=True, agent_name=self.agent_name,
                    user_message=f"🔎 **Review for {title}**\n\n{critique}",
                    updated_context=updated_ctx
                )

            # Fallback (should not be reached)
            msg = "I couldn't determine the review mode. Send `review: <Text>` or `review chapter 2.3`."
            return AgentResponse(
                success=False, agent_name=self.agent_name,
                instructions=[AgentInstruction(
                    requesting_agent=self.agent_name, action_type="ask_user", target="user",
                    message=msg, reasoning="Ambiguous review request."
                )],
                user_message=msg, updated_context=updated_ctx
            )

        except Exception as e:
            logger.error(f"[ReviewerAgent] Error: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                user_message=f"An error occurred: {e}",
                updated_context=context
            )

    # ---------- Core LLM call ----------
    def _review_with_llm(self, text: str, style_guide: str, citation_style: str, guardrails: str, multi_section: bool = False) -> str:
        """
        Critical review rubric with actionable suggestions.
        """
        sys = (
            "You are a **Critical Reviewer Agent** for academic theses.\n"
            "Act like a rigorous supervisor: pinpoint unclear phrasing, shallow reasoning, missing evidence,\n"
            "redundancy, logical gaps, structure issues, and citation/style inconsistencies.\n"
            "Be concise but specific. Always propose **actionable** improvements."
        )
        # include guardrails (if any)
        if guardrails:
            sys += f"\n\n# Guardrails (project rules)\n{guardrails}\n"

        style_block = (
            f"# Style Consistency\n"
            f"- style_guide: {style_guide}\n"
            f"- citation_style: {citation_style}\n"
        )

        mode = "MULTI-SECTION BATCH" if multi_section else "SINGLE PASSAGE"
        user = f"""Review Mode: {mode}

{style_block}

## TEXT TO REVIEW
{text}

## OUTPUT FORMAT (Markdown)
- **Clarity & Coherence:** concrete notes
- **Depth & Evidence:** missing citations, weak claims, how to strengthen
- **Argumentation & Logic:** fallacies, gaps, ordering
- **Redundancy & Focus:** what to cut or merge
- **Terminology & Consistency:** align with style_guide and citation_style
- **Actionable Revisions (checklist):** bullet list of edits
- **Suggested citations (if obvious):** 2–5 plausible sources or bib hints (titles/authors/year if known)
"""

        messages = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
        out = self.client.chat_completion(messages, temperature=0.3, max_tokens=700)
        return (out or "").strip()

    # ---------- Parse target ----------
    def _parse_chapter_target(self, text: str) -> Optional[tuple[int, Optional[int]]]:
        """
        Return the LAST 'review chapter N[.M]' (or 'review kapitel N[.M]') found in the text.
        Also tolerates supervisor wrappers like 'Original request:' / "User's additional info:".
        """
        t = (text or "")
        # strip known wrappers
        t = re.sub(r"(?i)original request:\s*", " ", t)
        t = re.sub(r"(?i)user'?s additional info:\s*", " ", t)
        t = re.sub(r"\s+", " ", t).strip()

        # find ALL matches, pick the last one
        pattern = re.compile(r"\breview\s+(?:chapter|kapitel)\s+(\d+)(?:\.(\d+))?\b", re.IGNORECASE)
        matches = list(pattern.finditer(t))
        if not matches:
            return None
        m = matches[-1]
        ch = int(m.group(1))
        sec = int(m.group(2)) if m.group(2) else None
        return ch, sec

    # ---------- File resolution (robust) ----------
    def _resolve_chapter_dir(self, ch_idx: int) -> Optional[str]:
        """
        Find the chapter directory by 2-digit prefix: data/thesis/chapter/NN_*
        """
        pat = os.path.join(CHAPTERS_ROOT, f"{ch_idx:02d}_*")
        matches = sorted(glob.glob(pat))
        return matches[0] if matches else None

    def _resolve_section_file(self, ch_dir: str, ch_idx: int, sec_idx: int) -> Optional[str]:
        """
        Find a section file in the directory `ch_dir`, e.g.:
        - 8.3.md
        - 08.03.md
        - 8.3_*.md / 08.03_*.md
        - 8-3*.md / 08-03*.md
        - sec_8_3*.md / sec_08_03*.md
        - 8.3_*  (occasionally without .md)
        """
        if not os.path.isdir(ch_dir):
            return None

        def _all_files():
            try:
                return [f for f in os.listdir(ch_dir) if os.path.isfile(os.path.join(ch_dir, f))]
            except Exception:
                return []

        files = _all_files()
        if not files:
            return None

        # Normalize filenames for comparison (lowercase)
        norm = [(fn, fn.lower()) for fn in files]

        d  = ch_idx
        dd = f"{ch_idx:02d}"
        s  = sec_idx
        ss = f"{sec_idx:02d}"

        # Candidate patterns (no regex chars), order = priority
        patterns = [
            f"{d}.{s}.md",      f"{dd}.{ss}.md",
            f"{d}.{s}_",        f"{dd}.{ss}_",      # common case: 8.3_<title>.md
            f"{d}-{s}.md",      f"{dd}-{ss}.md",
            f"{d}-{s}_",        f"{dd}-{ss}_",
            f"sec_{d}_{s}.md",  f"sec_{dd}_{ss}.md",
            f"sec_{d}_{s}_",    f"sec_{dd}_{ss}_",
            f"{d}.{s}",         f"{dd}.{ss}",       # without .md (just in case)
            f"{d}-{s}",         f"{dd}-{ss}",
            f"sec_{d}_{s}",     f"sec_{dd}_{ss}",
        ]

        # 1) Exact prefix match — covers "8.3_<title>.md"
        for pat in patterns:
            for orig, low in norm:
                if low.startswith(pat):
                    return os.path.join(ch_dir, orig)

        # 2) Fallback: contains-like heuristics with word-boundary-ish regexes
        regexes = [
            re.compile(rf"(^|[^0-9]){dd}\.{ss}([^0-9]|$)"),
            re.compile(rf"(^|[^0-9]){d}\.{s}([^0-9]|$)"),
            re.compile(rf"(^|[^0-9]){dd}-{ss}([^0-9]|$)"),
            re.compile(rf"(^|[^0-9]){d}-{s}([^0-9]|$)"),
        ]
        for orig, low in norm:
            for rx in regexes:
                if rx.search(low):
                    return os.path.join(ch_dir, orig)

        return None

    def _load_markdown_for_review(self, ch_idx: int, sec_idx: Optional[int]) -> tuple[str, str]:
        ch_dir = self._resolve_chapter_dir(ch_idx)
        if not ch_dir:
            return "", f"No chapter directory found for {ch_idx} (expected: `{ch_idx:02d}_*`)."

        logger.info(f"[ReviewerAgent] chapter dir resolved: {ch_dir}")

        if sec_idx is None:
            parts = []
            for fn in sorted(os.listdir(ch_dir)):
                if fn.lower().endswith(".md"):
                    try:
                        with open(os.path.join(ch_dir, fn), "r", encoding="utf-8", errors="ignore") as f:
                            parts.append(f.read().strip())
                    except Exception as e:
                        logger.warning(f"[ReviewerAgent] could not read {fn}: {e}")
            text = "\n\n".join(parts).strip()
            return (text, "") if text else ("", f"No Markdown found in chapter {ch_idx}.")
        else:
            fpath = self._resolve_section_file(ch_dir, ch_idx, sec_idx)
            logger.info(f"[ReviewerAgent] section file resolved: {fpath}")
            if not fpath:
                return "", f"No file found for chapter {ch_idx}.{sec_idx}."
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read().strip(), ""
            except Exception as e:
                return "", f"Section file could not be read: {e}"

    # Compatibility wrapper for previous callers
    def _load_section_markdown(self, outline: Optional[ThesisOutline], ch_idx: int, sec_idx: Optional[int]) -> str:
        text, err = self._load_markdown_for_review(ch_idx, sec_idx)
        return text if not err else ""

    def _find_all_sections(self) -> List[str]:
        return [p for p in glob.glob(SECTION_GLOB, recursive=True) if os.path.isfile(p)]

    # ---------- Titles / outline formatting ----------
    def _title_for(self, outline: Optional[ThesisOutline], ch_idx: int, sec_idx: Optional[int]) -> str:
        if not outline:
            return f"Chapter {ch_idx}" + (f".{sec_idx}" if sec_idx else ".0")
        try:
            if sec_idx:
                return f"Chapter {ch_idx}.{sec_idx}: {outline.chapters[ch_idx-1].sections[sec_idx-1].title}"
            return f"Chapter {ch_idx}.0: {outline.chapters[ch_idx-1].title}"
        except Exception:
            return f"Chapter {ch_idx}" + (f".{sec_idx}" if sec_idx else ".0")

    def _format_outline_for_prompt(self, outline: Optional[ThesisOutline]) -> str:
        if not outline:
            return ""
        lines = []
        for i, ch in enumerate(outline.chapters or [], 1):
            ch_title = _strip_leading_enumeration(getattr(ch, "title", "") or f"Chapter {i}")
            lines.append(f"{i}.0 {ch_title}")
            secs = getattr(ch, "sections", []) or []
            for j, sec in enumerate(secs, 1):
                sec_title = _strip_leading_enumeration(getattr(sec, "title", "") or f"Section {i}.{j}")
                lines.append(f"  {i}.{j} {sec_title}")
        return "```\n" + "\n".join(lines) + "\n```"

    def _section_to_thesis_outline(self, root: OutlineSection) -> ThesisOutline:
        chapters: list[OutlineChapter] = []
        for ch in (root.subsections or []):
            chapters.append(
                OutlineChapter(
                    title=ch.title,
                    sections=[OutlineSection(title=s.title) for s in (ch.subsections or [])]
                )
            )
        return ThesisOutline(title=root.title or "Thesis", chapters=chapters)

    # ---------- Guardrails ----------
    def _read_guardrail_docs(self, max_chars: int = 6000) -> str:
        """
        Reuse guardrail .md/.txt from data/thesis/guardrails (same logic as in writing agent).
        """
        try:
            files = list_guardrail_files()
        except Exception:
            files = []

        files = [p for p in files if os.path.splitext(p)[1].lower() in {".md", ".txt"}]
        if not files:
            return ""

        sig_src = []
        for p in sorted(files):
            try:
                sig_src.append(p + str(os.path.getmtime(p)))
            except Exception:
                sig_src.append(p)
        sig = hashlib.sha256("|".join(sig_src).encode("utf-8")).hexdigest()

        if self._guardrails_cache and self._guardrails_cache.get("sig") == sig:
            return self._guardrails_cache.get("text", "")

        parts = []
        for p in files:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read().strip()
                relname = os.path.basename(p)
                parts.append(f"\n---\n# Guardrail: {relname}\n{txt}\n")
            except Exception:
                continue

        blob = "\n".join(parts).strip()
        if len(blob) > max_chars:
            # Light truncation; prefer simplicity here
            blob = blob[:max_chars] + "\n… (truncated)"
        self._guardrails_cache = {"sig": sig, "text": blob}
        return blob

    def _update_context_from_input_basic(self, user_input: str, context: UserContext) -> UserContext:
        """
        Minimal enrichment: load the latest saved outline into context
        so the agent can name chapters/sections.
        """
        if not getattr(context, "latest_outline", None):
            sec = load_latest_outline()
            if sec:
                context.latest_outline = self._section_to_thesis_outline(sec)
        return context

    def _has_enough_info_review(
        self,
        *,
        inline_match: Optional[re.Match],
        wants_all: bool,
        target_pair: Optional[tuple[int, Optional[int]]]
    ) -> tuple[bool, dict]:
        """
        Returns (ok, missing_dict).
        ok == True if one of the valid review intents is available:
        - inline text after `review:`
        - explicit 'review all'
        - a concrete chapter/section like 2.3
        """
        missing = {
            "inline": inline_match is None,
            "all": not wants_all,
            "target": target_pair is None,
        }
        # enough if ANY of the three modes is provided
        ok = bool(inline_match or wants_all or target_pair)
        return ok, missing


    def _get_next_question_review(self, context: UserContext, *, outline: Optional[ThesisOutline]) -> str:
        """
        Ask for the next best piece of information to proceed.
        Order of preference:
        1) inline text
        2) a specific chapter/section (e.g., 3.2)
        3) 'review all'
        """
        menu = self._format_outline_for_prompt(outline) if outline else ""
        help_msg = (
            "What should I review?\n"
            "- `review: <Your text>`\n"
            "- `review chapter 2.3` (or `review kapitel 2.3`)\n"
            "- `review all`\n"
        ) + (("\nCurrent outline:\n" + menu) if menu else "")
        return help_msg

