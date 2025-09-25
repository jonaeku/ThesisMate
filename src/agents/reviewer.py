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

# --- IMPORTANT: matches your real layout like
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
        Triggers on: 'review', 'kritik', 'bewerte', 'feedback', 'überarbeiten'.
        """
        t = (user_input or "").lower()
        if re.search(r"\b(review|feedback|kritik|bewerte|überarbeit|ueberarbeit)\b", t):
            return AgentCapabilityAssessment(can_handle=True, confidence=0.9, missing_info=[], reasoning="Review intent detected", suggested_questions=[])
        # be generous but safe
        return AgentCapabilityAssessment(can_handle=False, confidence=0.4, missing_info=[], reasoning="No explicit review intent", suggested_questions=[])

    # ---------- MAIN ----------
    def process_request(self, user_input: str, context: UserContext, options: Optional[dict] = None) -> AgentResponse:
        """
        Three modes:
        - 'review: <text>'  → inline review of supplied passage
        - 'review chapter 2.3' / 'review kapitel 2.3'  → review saved section
        - 'review all'      → brief pass on all sections
        """
        logger.info(f"[ReviewerAgent] processing: {user_input[:160]}")
        options = options or {}
        t = (user_input or "").strip()

        # 0) load global style & guardrails text (for prompt conditioning)
        style_json = get_global_style() or {}
        style_guide_text = style_json.get("style_guide", "")
        citation_style   = style_json.get("citation_style", "APA")
        guardrail_text   = self._read_guardrail_docs(max_chars=6000)  # reuses guardrail .md/.txt

        # --- Mode 1: inline passage after "review:" ---
        m = re.search(r"\breview\s*:\s*(.+)$", t, flags=re.I | re.S)
        if m:
            passage = m.group(1).strip()
            if not passage:
                return AgentResponse(
                    success=False, agent_name=self.agent_name,
                    user_message="Bitte hänge nach `review:` den zu prüfenden Text an."
                )
            critique = self._review_with_llm(passage, style_guide_text, citation_style, guardrail_text)
            return AgentResponse(
                success=True, agent_name=self.agent_name,
                user_message=f"🧪 **Review (inline passage)**\n\n{critique}",
                updated_context=context
            )

        # Prepare outline if needed
        outline = getattr(context, "latest_outline", None)
        if not outline:
            sec = load_latest_outline()
            if sec:
                outline = self._section_to_thesis_outline(sec)
                context.latest_outline = outline

        # --- Mode 2: review chapter X[.Y] ---
        target = self._parse_chapter_target(t)
        if target:
            ch_idx, sec_idx = target
            md, err = self._load_markdown_for_review(ch_idx, sec_idx)
            if err:
                msg = f"⚠️ {err}\n(Tipp: Abschnittsdatei darf z. B. `08.03.md`, `8.3.md`, `8-3.md` heißen.)"
                return AgentResponse(
                    success=False, agent_name=self.agent_name,
                    instructions=[AgentInstruction(
                        requesting_agent=self.agent_name, action_type="ask_user", target="user",
                        message=msg, reasoning="No saved section markdown found."
                    )],
                    user_message=msg, updated_context=context
                )
            critique = self._review_with_llm(md, style_guide_text, citation_style, guardrail_text)
            title = self._title_for(outline, ch_idx, sec_idx)
            return AgentResponse(
                success=True, agent_name=self.agent_name,
                user_message=f"🔎 **Review für {title}**\n\n{critique}",
                updated_context=context
            )

        # --- Mode 3: review all ---
        if re.search(r"\breview\s+all\b", t, flags=re.I):
            found = self._find_all_sections()
            if not found:
                return AgentResponse(
                    success=False, agent_name=self.agent_name,
                    user_message="Ich habe keine gespeicherten Abschnitte gefunden.",
                    updated_context=context
                )
            # quick pass (limit n to keep prompt sizes reasonable)
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
                user_message=f"🧵 **Gesamt-Review (Auszug, bis 12 Abschnitte)**\n\n{critique}",
                updated_context=context
            )

        # Nothing matched → ask user what to review
        menu = self._format_outline_for_prompt(outline) if outline else ""
        help_msg = (
            "Wie soll ich reviewen?\n"
            "- `review: <Dein Text>`\n"
            "- `review chapter 2.3` (oder `review kapitel 2.3`)\n"
            "- `review all`\n"
        ) + (("\nAktuelle Gliederung:\n" + menu) if menu else "")
        return AgentResponse(
            success=False, agent_name=self.agent_name,
            instructions=[AgentInstruction(
                requesting_agent=self.agent_name, action_type="ask_user", target="user",
                message=help_msg, reasoning="Need explicit review scope."
            )],
            user_message=help_msg, updated_context=context
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
        Find chapter dir by 2-digit prefix: data/thesis/chapter/NN_*
        """
        pat = os.path.join(CHAPTERS_ROOT, f"{ch_idx:02d}_*")
        matches = sorted(glob.glob(pat))
        return matches[0] if matches else None

    def _resolve_section_file(self, ch_dir: str, ch_idx: int, sec_idx: int) -> Optional[str]:
        """
        Findet eine Abschnittsdatei im Ordner `ch_dir`, z.B.:
        - 8.3.md
        - 08.03.md
        - 8.3_*.md / 08.03_*.md
        - 8-3*.md / 08-03*.md
        - sec_8_3*.md / sec_08_03*.md
        - 8.3_*  (falls ausnahmsweise ohne .md gespeichert)
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

        # Normalisiere Dateinamen für den Vergleich (lowercase, Backslashes → Slashes)
        norm = [(fn, fn.lower()) for fn in files]

        d  = ch_idx
        dd = f"{ch_idx:02d}"
        s  = sec_idx
        ss = f"{sec_idx:02d}"

        # Kandidatenmuster (ohne Regex-Sonderzeichen), Reihenfolge = Priorität
        patterns = [
            f"{d}.{s}.md",      f"{dd}.{ss}.md",
            f"{d}.{s}_",        f"{dd}.{ss}_",      # dein Fall: 8.3_<titel>.md
            f"{d}-{s}.md",      f"{dd}-{ss}.md",
            f"{d}-{s}_",        f"{dd}-{ss}_",
            f"sec_{d}_{s}.md",  f"sec_{dd}_{ss}.md",
            f"sec_{d}_{s}_",    f"sec_{dd}_{ss}_",
            f"{d}.{s}",         f"{dd}.{ss}",       # ohne .md (zur Sicherheit)
            f"{d}-{s}",         f"{dd}-{ss}",
            f"sec_{d}_{s}",     f"sec_{dd}_{ss}",
        ]

        # 1) Exakter Start-mit-Prüfer (prefix match) – deckt "8.3_<titel>.md"
        for pat in patterns:
            for orig, low in norm:
                if low.startswith(pat):
                    return os.path.join(ch_dir, orig)

        # 2) Fallback: enthält-Match mit Wortgrenzen-ähnlicher Heuristik
        #    (hilfreich, falls z.B. Whitespaces oder andere Separatoren)
    
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
            return "", f"Kein Kapitel-Ordner für {ch_idx} gefunden (erwartet: `{ch_idx:02d}_*`)."

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
            return (text, "") if text else ("", f"Kein Markdown im Kapitel {ch_idx} gefunden.")
        else:
            fpath = self._resolve_section_file(ch_dir, ch_idx, sec_idx)
            logger.info(f"[ReviewerAgent] section file resolved: {fpath}")
            if not fpath:
                return "", f"Für Kapitel {ch_idx}.{sec_idx} wurde keine Datei gefunden."
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read().strip(), ""
            except Exception as e:
                return "", f"Abschnittsdatei konnte nicht gelesen werden: {e}"


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
            # light truncation with preference for headings and bullets is possible; keep simple here
            blob = blob[:max_chars] + "\n… (truncated)"
        self._guardrails_cache = {"sig": sig, "text": blob}
        return blob
