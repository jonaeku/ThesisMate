from __future__ import annotations
import hashlib
import os
import json
import glob
from typing import Optional, List, Tuple
import re
from src.utils.logging import get_logger
from src.utils.openrouter_client import OpenRouterClient
from src.utils.storage import (
    _strip_leading_enumeration, list_guardrail_files, load_guardrails, load_writing_style, save_guardrail_files, save_guardrails,
    save_passage, load_latest_outline
)
from src.models.models import (
    UserContext,
    AgentResponse, AgentInstruction, AgentCapabilityAssessment,
    ThesisOutline, DraftPassage, WritingStyleConfig, GuardrailsConfig,
    OutlineSection, OutlineChapter
)

from src.utils.style_store import get_style as get_global_style, save_style as save_global_style


logger = get_logger(__name__)
PAPERS_DIR_GLOB = "data/**/*.json"

class WritingAssistantAgent:
    def __init__(self, research_tool=None):
        self.client = OpenRouterClient()
        self.research_tool = research_tool
        self.agent_name = "writing_assistant"

    # ---------- CAPABILITY ----------
    def can_handle_request(self, user_input: str, context: UserContext) -> AgentCapabilityAssessment:
        """
        Fast LLM check whether this is a drafting/editing request (YES/NO).
        """
        try:
            prompt = f"""You are a Writing Agent for academic theses.

Analyze if the user wants help drafting or refining academic paragraphs/sections.

User input: "{user_input}"

You CAN handle:
- Draft paragraph/section from keywords
- Improve academic tone, consistency, citation style
- Insert inline citations (APA/MLA/etc.)
- Use BibTeX entries/research notes if available

You CANNOT handle:
- Building full outlines (that's structure agent)
- Deep literature search (research agent only)

Answer ONLY "YES" or "NO" and a short reason."""
            messages = [
                {"role": "system", "content": "Be generous; most drafting/editing asks are YES."},
                {"role": "user", "content": prompt}
            ]
            out = self.client.chat_completion(messages, temperature=0.1, max_tokens=60)
            if out and "YES" in out.upper():
                return AgentCapabilityAssessment(can_handle=True, confidence=0.9, missing_info=[], reasoning="Drafting/editing", suggested_questions=[])
            if out and "NO" in out.upper():
                return AgentCapabilityAssessment(can_handle=False, confidence=0.9, missing_info=[], reasoning=out.strip(), suggested_questions=[])
            return AgentCapabilityAssessment(can_handle=True, confidence=0.7, missing_info=[], reasoning="Assuming drafting/editing", suggested_questions=[])
        except Exception as e:
            logger.warning(f"can_handle_request failed: {e}")
            return AgentCapabilityAssessment(can_handle=True, confidence=0.6, missing_info=[], reasoning=str(e), suggested_questions=[])

    # ---------- MAIN ----------
    def process_request(
        self,
        user_input: str,
        context: UserContext,
        options: Optional[dict] = None,
    ) -> AgentResponse:
        """
        Topic-Agent style:
        1) Enrich context
        2) Capability check
        3) Gate: Do we have enough info? → ask a targeted question
        4) Draft paragraph
        5) (optional) Validations
        6) Format & return
        """
        logger.info(f"[WritingAgent] processing: {user_input[:120]}")
        options = options or {}

        try:

             # --- 0) FAST PATH: handle style commands up-front ---
        # do NOT depend on outline/targets; these commands should always work
            style_json = get_global_style() or {}
            style_for_cmds = (
                getattr(context, "writing_style", None)
                or load_writing_style()
                or self._default_style(context)
            )
            cmd_resp = self._handle_style_commands(user_input, style_json, style_for_cmds)
            if cmd_resp:
                return cmd_resp
            # ---------------- 1) Enrich context ----------------
            updated_ctx = self._update_context_from_input_basic(user_input, context)

            # ---------------- 2) Capability check ---------------
            assessment = None
            if hasattr(self, "can_handle_request"):
                try:
                    assessment = self.can_handle_request(user_input, updated_ctx)
                except Exception as e:
                    logger.warning(f"[WritingAgent] can_handle_request failed, assuming YES: {e}")

            if assessment and not assessment.can_handle:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    capability_assessment=assessment,
                    user_message=f"I can't help with this request. {assessment.reasoning}",
                    updated_context=updated_ctx,
                )

            # ---------------- 3) Gate: Do we have enough info? --
            # Minimal requirements to write:
            #   a) outline present
            #   b) concrete target (chapter/section)
            #   c) seeds (keywords/draft)
            outline = updated_ctx.latest_outline
            seeds = self._extract_seed_content(user_input)

            target = None
            if outline:
                target = self._extract_target_location(user_input, outline)
                if target is None:
                    # optionally allow loose extraction as a second try
                    target = self._extract_target_location_loose(user_input)

            has_all, _missing = self._has_enough_info_writing(outline=outline, target=target, seeds=seeds)
            if not has_all:
                question = self._get_next_question_writing(updated_ctx, outline=outline, target=target, seeds=seeds)
                instr = AgentInstruction(
                    requesting_agent=self.agent_name,
                    action_type="ask_user",
                    target="user",
                    message=question,
                    reasoning="Need this information to write a suitable paragraph."
                )
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    instructions=[instr],
                    user_message=question,
                    updated_context=updated_ctx
                )

            # ---------------- 4) Draft (existing pipeline) -------
            # 4.0 Load style/guardrails
            style = updated_ctx.writing_style or load_writing_style() or self._default_style(updated_ctx)
            guard = updated_ctx.guardrails or load_guardrails() or self._default_guardrails()

            # 4.1 Enforce global style (if present)
            style_json = get_global_style()  # {"style_guide": "...", "citation_style": "APA"}
            if style_json.get("citation_style"):
                try:
                    style.citation_style = style_json["citation_style"]
                except Exception:
                    pass
            style_guide_text = style_json.get("style_guide", "")

            # 4.2 Style commands in user_input (early exit if matched)
            style_cmd_resp = self._handle_style_commands(user_input, style_json, style)
            if style_cmd_resp:
                return style_cmd_resp

            # 4.3 Uploads (guardrails)
            incoming = options.get("files") or []
            normalized: list[tuple[str, bytes]] = []
            for f in incoming:
                if isinstance(f, dict) and "name" in f and "content" in f:
                    normalized.append((f["name"], f["content"]))
                elif isinstance(f, (list, tuple)) and len(f) == 2:
                    normalized.append((f[0], f[1]))
            saved_msg = ""
            if normalized:
                try:
                    allowed = getattr(guard, "allowed_extensions", None)
                    saved_paths = save_guardrail_files(normalized, allowed_ext=allowed, max_mb=25)
                    updated_ctx.guardrail_files = list_guardrail_files()
                    saved_msg = f"📁 {len(saved_paths)} file(s) saved to guardrails."
                except Exception as e:
                    return AgentResponse(
                        success=False,
                        agent_name=self.agent_name,
                        instructions=[],
                        user_message=f"Upload failed: {e}",
                        updated_context=updated_ctx
                    )

            # 4.4 Target info
            ch_idx, sec_idx, sec_title = target
            section_name = sec_title or outline.chapters[ch_idx - 1].title

            # 4.5 (Optional) Update configs from input
            style, guard, style_changed = self._maybe_update_configs_from_input(user_input, style, guard)
            if style_changed:
                updated_ctx.writing_style = style
                updated_ctx.guardrails = guard

            # 4.6 Bib keys & sources
            bib_keys = self._collect_bib_keys_from_input(user_input)
            all_papers = self._load_papers_from_disk()
            topic_hint = getattr(updated_ctx, "chosen_topic", None) or getattr(updated_ctx, "topic_title", None) or ""
            best_papers = self._pick_best_papers(all_papers, topic_hint=topic_hint, seeds=seeds, section_title=section_name)
            sources_txt = self._format_sources_for_prompt(best_papers)

            # 4.7 LLM draft
            paragraph_md, used_citations = self._draft_paragraph(
                seeds, style, guard, outline, ch_idx, sec_idx, sec_title, bib_keys, style_guide_text, sources_txt
            )

            # 4.8 Apply local guardrails
            paragraph_md = self._apply_local_guardrails(paragraph_md, style, guard)

            # 4.9 Persist
            draft = DraftPassage(
                chapter_index=ch_idx,
                section_index=sec_idx,
                title=sec_title,
                content_markdown=paragraph_md,
                citations=used_citations
            )
            merge = (options or {}).get("merge_strategy", "append")
            m = re.search(r"\bmerge\s*=\s*(append|overwrite|version|revise)\b", user_input, flags=re.I)
            if m:
                merge = m.group(1).lower()

            saved = save_passage(outline, draft, merge_strategy=merge)

            # ---------------- 5) UI formatting -------------------
            title_line = self._make_title_line(ch_idx, sec_idx, sec_title or outline.chapters[ch_idx - 1].title)
            ui = (f"✍️ **New paragraph saved** → `{saved['file']}`\n\n"
                f"{title_line}\n\n"
                f"{paragraph_md}")
            if saved_msg:
                ui = saved_msg + "\n\n" + ui

            # ---------------- 6) Return --------------------------
            return AgentResponse(
                success=True,
                agent_name=self.agent_name,
                result=draft,
                user_message=ui,
                updated_context=updated_ctx
            )

        except Exception as e:
            logger.error(f"[WritingAgent] Error: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                user_message=f"An error occurred: {e}",
                updated_context=context,
            )


    # ---------- Helpers ----------

    def _has_enough_info_writing(self, *, outline, target, seeds: str) -> tuple[bool, dict]:
        """
        Returns (ok, missing_dict) where missing_dict flags which pieces are missing.
        ok == True only if outline, target and seeds are all present.
        """
        missing = {
            "outline": outline is None,
            "target": target is None,
            "seeds": not bool(seeds and seeds.strip()),
        }
        ok = not any(missing.values())
        return ok, missing


    def _get_next_question_writing(self, context: UserContext, *, outline, target, seeds: str) -> str:
        """
        Asks exactly for the next missing piece in a user-friendly order:
        1) outline, 2) target (chapter/section), 3) seeds.
        """
        if outline is None:
            return "I need your thesis outline to know where the text belongs. Please create or load an outline first."

        if target is None:
            menu = self._format_outline_for_prompt(context.latest_outline) if getattr(context, "latest_outline", None) else ""
            return ("Which section should I write for? Reply with a number like **3.2** or a section title.\n" + menu).strip()

        if not seeds or not seeds.strip():
            return "Please send keywords or a rough draft for the paragraph, e.g.: `Keywords: federated learning, radiology, privacy`."

        # Should not be reached, but keep a safe fallback:
        return "What exactly should I write? Please specify section and a few keywords."

    def _update_context_from_input_basic(self, user_input: str, context: UserContext) -> UserContext:
        """
        Minimal enrichment (Topic-Agent style):
        - If no outline is in context, try loading the latest saved one.
        - Otherwise leave context unchanged.
        """
        if not getattr(context, "latest_outline", None):
            sec = load_latest_outline()
            if sec:
                context.latest_outline = self._section_to_thesis_outline(sec)
        return context

    def _tokenize(self, text: str) -> set[str]:
        t = (text or "").lower()
        # sehr simple Tokenisierung
        return set(re.findall(r"[a-zA-Zäöüß0-9\-]+", t))

    def _load_papers_from_disk(self) -> list[dict]:
        """
        Read all papers_*.json (list-of-dicts OR JSONL) recursively from data/…
        """
        items: list[dict] = []
        for path in glob.glob(PAPERS_DIR_GLOB, recursive=True):
            if "papers_" not in os.path.basename(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read().strip()
                if not txt:
                    continue
                # Entweder eine Liste [...]
                if txt.lstrip().startswith("["):
                    items.extend(json.loads(txt))
                else:
                    # Oder JSONL
                    for line in txt.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        items.append(json.loads(line))
            except Exception as e:
                logger.warning(f"Could not read papers file {path}: {e}")
        return items

    def _score_paper_for_section(self, paper: dict, topic_hint: str, seeds: str, section_title: str) -> float:
        """
        Combined score:
        - 0.7 * stored relevance_score (0..1, fallback 0.3)
        - 0.3 * keyword overlap (0..1) with topic/seeds/section
        """
        base = float(paper.get("relevance_score") or 0.3)
        text = " ".join([
            paper.get("title") or "",
            " ".join(paper.get("authors") or []),
            paper.get("abstract") or "",
            paper.get("url") or "",
            paper.get("bibtex") or "",
        ])
        toks_doc   = self._tokenize(text)
        toks_query = self._tokenize(" ".join([topic_hint or "", seeds or "", section_title or ""]))
        overlap = 0.0
        if toks_doc and toks_query:
            overlap = len(toks_doc & toks_query) / max(1, len(toks_query))
            overlap = min(1.0, overlap)
        return 0.7 * base + 0.3 * overlap

    def _pick_best_papers(self, all_papers: list[dict], topic_hint: str, seeds: str, section_title: str,
                        min_score: float = 0.45, top_k: int = 6) -> list[dict]:
        """
        Filter + sort by combined score and return top_k.
        """
        scored = []
        for p in all_papers:
            s = self._score_paper_for_section(p, topic_hint, seeds, section_title)
            if s >= min_score:
                scored.append((s, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for s, p in scored[:top_k]]

    def _format_sources_for_prompt(self, items: list[dict]) -> str:
        if not items:
            return ""
        lines = []
        for it in items:
            authors = it.get("authors") or []
            author = ", ".join(authors[:2]) + (" et al." if len(authors) > 2 else "") if authors else "?"
            year   = it.get("year") or "n.d."
            title  = it.get("title") or "Untitled"
            url    = it.get("doi") or it.get("url") or ""
            lines.append(f"- {author} ({year}): {title}" + (f" — {url}" if url else ""))
        return "\n".join(lines)

    def _handle_style_commands(self, user_input: str, style_json: dict, style: WritingStyleConfig
    ) -> Optional[AgentResponse]:
        """
        Supports:
        - 'style show'
        - 'style set citation=<APA|MLA|Chicago|IEEE|Harvard>'
        - 'style set guide: <free text>' or 'style set guide=<free text>'
        Returns a fully-formed AgentResponse (success=True) if matched; otherwise None.
        """
        t = (user_input or "").strip()

        # --- SHOW ---
        if re.search(r"\bstyle\s+show\b", t, flags=re.I):
            msg = (
                "🧭 **Writing Style (global)**\n"
                f"- citation_style: **{style_json.get('citation_style','')}**\n"
                f"- style_guide:\n{style_json.get('style_guide','')}\n"
            )
            return AgentResponse(
                success=True,
                agent_name=self.agent_name,
                result=None,
                user_message=msg
            )
        
        # --- HELP ---
        if re.search(r"\bstyle\s+help\b", t, flags=re.I):
            return AgentResponse(
                success=True,
                agent_name=self.agent_name,
                user_message=(
                    "ℹ️ **Style Kommandos**\n"
                    "- `style show`\n"
                    "- `style set citation=APA` (MLA|Chicago|IEEE|Harvard)\n"
                    "- `style set guide: <Text>`\n"
                )
            )

        # --- SET citation ---
        m = re.search(r"\bstyle\s+set\s+citation\s*=\s*([A-Za-z]+)\b", t, flags=re.I)
        if m:
            new_cit = m.group(1).upper()
            # Normalisieren einiger Varianten
            map_norm = {"APA":"APA","MLA":"MLA","CHICAGO":"CHICAGO","IEEE":"IEEE","HARVARD":"HARVARD"}
            if new_cit in map_norm:
                style_json["citation_style"] = map_norm[new_cit]
                # auch in WritingStyleConfig spiegeln
                try:
                    style.citation_style = style_json["citation_style"]
                except Exception:
                    pass
                save_global_style(style_json)
                return AgentResponse(
                    success=True,
                    agent_name=self.agent_name,
                    user_message=f"✅ citation_style auf **{style_json['citation_style']}** gesetzt."
                )
            else:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    user_message=f"Unknown citation_style: {new_cit}. Allowed: APA, MLA, Chicago, IEEE, Harvard."
                )

        # --- SET guide (":" oder "=") ---
        m = re.search(r"\bstyle\s+set\s+guide\s*(?:=|:)\s*(.+)$", t, flags=re.I | re.S)
        if m:
            new_guide = m.group(1).strip()
            if new_guide:
                style_json["style_guide"] = new_guide
                save_global_style(style_json)
                return AgentResponse(
                    success=True,
                    agent_name=self.agent_name,
                    user_message="✅ style_guide updated.\n\n" + new_guide
                )
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                user_message="No style_guide text found. Use something like: `style set guide: Formal, concise …`"
            )

        return None

    def _make_title_line(self, ch_idx: int, sec_idx: Optional[int], title: str) -> str:
        hashes = "#" * max(1, min(6, 3))
        if sec_idx:
            return f"{hashes} Chapter {ch_idx}.{sec_idx}: {title}"
        return f"{hashes} Chapter {ch_idx}.0: {title}"

    def _format_outline_for_prompt(self, outline: ThesisOutline) -> str:
        """
        Show chapters + subsections, numbered as 1.0 / 1.1; strips leading numbers from titles.
        Returned as a code block to preserve indentation in chat UIs.
        """
        lines = []
        for i, ch in enumerate(outline.chapters or [], 1):
            ch_title = _strip_leading_enumeration(getattr(ch, "title", "") or f"Chapter {i}")
            lines.append(f"{i}.0 {ch_title}")
            secs = getattr(ch, "sections", []) or []
            for j, sec in enumerate(secs, 1):
                sec_title = _strip_leading_enumeration(getattr(sec, "title", "") or f"Section {i}.{j}")
                lines.append(f"  {i}.{j} {sec_title}")
        # Als Codeblock zurückgeben, damit die Einrückung im Chat sauber bleibt
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
        # root.title enthält den Thesis-Titel (so haben wir gespeichert)
        return ThesisOutline(title=root.title or "Thesis", chapters=chapters)

    def _default_style(self, context: UserContext) -> WritingStyleConfig:
        lang = "de" if (context and context.field and re.search(r"(medizin|wirtschaft|deutsch|recht)", (context.field or "").lower())) else "en"
        return WritingStyleConfig(language=lang)

    def _default_guardrails(self) -> GuardrailsConfig:
        return GuardrailsConfig()

    def _extract_target_location(self, text: str, outline: ThesisOutline) -> Optional[Tuple[int, Optional[int], Optional[str]]]:
        """
        Loose extraction of (chapter, section, optional title) from free text, e.g.:
        - "4.1 Something, keywords: ..."
        - "Chapter 3.2 Federated Learning in Radiology"
        - "chapter 2 Related Work"
        Return: (chapter_index, section_index|None, extracted_title|None)
        """
        t = (text or "").strip().lower()

        # 3.2 / kapitel 3.2
        m = re.search(r"(kapitel|chapter)?\s*(\d+)\.(\d+)", t)
        if m:
            ch = int(m.group(2)); sec = int(m.group(3))
            if 1 <= ch <= len(outline.chapters):
                chap = outline.chapters[ch-1]
                if 1 <= sec <= len(chap.sections):
                    return ch, sec, chap.sections[sec-1].title
                return ch, sec, None

        # kapitel 3 / chapter 3
        m = re.search(r"(kapitel|chapter)\s*(\d+)", t)
        if m:
            ch = int(m.group(2))
            if 1 <= ch <= len(outline.chapters):
                return ch, None, outline.chapters[ch-1].title

        # Nur Nummern z. B. "3.0"
        m = re.search(r"\b(\d+)\.0\b", t)
        if m:
            ch = int(m.group(1))
            if 1 <= ch <= len(outline.chapters):
                return ch, None, outline.chapters[ch-1].title

        # Section-Titel fuzzy match
        for i, ch in enumerate(outline.chapters, 1):
            if ch.title and ch.title.lower() in t:
                return i, None, ch.title
            for j, sec in enumerate(ch.sections, 1):
                if sec.title and sec.title.lower() in t:
                    return i, j, sec.title

        return None

    def _extract_seed_content(self, text: str) -> str:
        """
        Extract seeds (keywords/draft). Accepts patterns like `Keywords: ...`, `Draft: ...`,
        otherwise returns the full input without steering phrases.
        """
        m = re.search(r"(?:keywords?|stichw(?:örter)?|draft|entwurf)\s*[:：]\s*(.+)", text, flags=re.I)
        if m:
            return m.group(1).strip()
        # Andernfalls: räume Steuerpräfixe weg
        cleaned = re.sub(r"(kapitel|chapter)\s*\d+(\.\d+)?", "", text, flags=re.I)
        return cleaned.strip()

    def _maybe_update_configs_from_input(
        self, text: str, style: WritingStyleConfig, guard: GuardrailsConfig
    ) -> Tuple[WritingStyleConfig, GuardrailsConfig, bool]:
        changed = False
        t = text.lower()

        # Citation style
        for c in ["apa", "mla", "chicago", "ieee", "harvard"]:
            if re.search(rf"\b{c}\b", t):
                if style.citation_style.lower() != c:
                    style.citation_style = c.upper() if c != "ieee" else "IEEE"
                    changed = True

        # Sprache
        if "sprache: de" in t or "language: de" in t:
            if style.language != "de": style.language = "de"; changed = True
        if "sprache: en" in t or "language: en" in t:
            if style.language != "en": style.language = "en"; changed = True

        # Ton
        if "formal" in t and style.academic_style != "formal":
            style.academic_style = "formal"; changed = True
        if "concise" in t and style.academic_style != "concise":
            style.academic_style = "concise"; changed = True

        # Guardrails (einfach)
        if "allow uploads" in t or "dateiupload erlauben" in t:
            if not guard.allow_file_uploads: guard.allow_file_uploads = True; changed = True
        if "disallow uploads" in t or "dateiupload verbieten" in t:
            if guard.allow_file_uploads: guard.allow_file_uploads = False; changed = True

        return style, guard, changed

    def _collect_bib_keys_from_input(self, text: str) -> List[str]:
        """
        Allowed [@Smith2020; @Miller19]. Returns list of Keys.
        """
        keys = re.findall(r"\[@([\w:-]+)\]", text)  # einzelne
        # Mehrfachtrenner ; oder , innerhalb [@a; @b]
        group = re.findall(r"\[@([^\]]+)\]", text)
        for g in group:
            for part in re.split(r"[;,]\s*", g):
                m = re.match(r"@?([\w:-]+)", part.strip())
                if m:
                    k = m.group(1)
                    if k not in keys:
                        keys.append(k)
        return keys

    def _draft_paragraph(
        self, seeds: str, style: WritingStyleConfig, guard: GuardrailsConfig,
        outline: ThesisOutline, ch_idx: int, sec_idx: Optional[int], sec_title: Optional[str],
        bib_keys: List[str], style_guide_text: str, sources_txt: str 
    ) -> Tuple[str, List[str]]:
        lang = "German" if style.language == "de" else "English"
        section_hint = f"Chapter {ch_idx}" + (f".{sec_idx}" if sec_idx else "")
        section_name = sec_title or outline.chapters[ch_idx-1].title
        guardrail_text = self._read_guardrail_docs(max_chars=8000)


        sys = (
            "You are a precise academic writing assistant. "
            "Write in rigorous academic tone, avoid plagiarism; paraphrase and cite where needed. "
            "Return Markdown only."
        )

        if guardrail_text:
            sys += (f"{guardrail_text}\n")

        style_lookup_txt = (
            f"Look Up Writing Style --> Consistency\n"
            f"- style_guide: {style_guide_text}\n"
            f"- citation_style: {style.citation_style}\n"
        )

        sources_block = f"\nUse these vetted sources when making claims:\n{sources_txt}\n" if sources_txt else ""

        user = f"""Write a polished academic paragraph for the thesis section **{section_hint}: {section_name}**.

{style_lookup_txt}
{sources_block}
Language: {lang}
Tone/Style: {style.academic_style}, {style.voice}, tense={style.tense}, audience={style.target_readability}
Citation style: {style.citation_style}
Constraints:
- Avoid first person if disallowed: {guard.disallow_first_person}
- Prefer terms: {style.preferred_terms}
- Avoid phrases: {style.avoid_phrases}
- Provide inline citations where claims are made. If no reliable source is known, write cautiously.

Seeds (keywords/draft):
{seeds}

STRICT OUTPUT RULES:
- Produce EXACTLY ONE compact Markdown paragraph (4–7 sentences).
- DO NOT include any headings/titles (no leading '#').
- DO NOT include lists, bullets, numbering, blockquotes, or code fences.
- Inline citations are allowed, e.g., (Author, Year) for APA/Harvard/Chicago; [#] for IEEE; (Author Page) for MLA.
"""
        messages = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
        md = self.client.chat_completion(messages, temperature=0.5, max_tokens=400).strip()

        # einfache IEEE-Nummern nicht generieren – wir lassen generisch (Author, Year)
        used = bib_keys  # (hier optional erweitern, falls LLM Keys nennt)
        return md, used

    def _apply_local_guardrails(self, md: str, style: WritingStyleConfig, guard: GuardrailsConfig) -> str:
        # 1) Verbiete Ich-Formen
        if guard.disallow_first_person:
            md = re.sub(r"\b(I|we|We|Ich|wir|Wir)\b", " ", md)
            md = re.sub(r"\s+", " ", md).strip()

        # 2) Verbote Phrasen
        for p in style.avoid_phrases or []:
            md = re.sub(re.escape(p), "", md, flags=re.IGNORECASE)

        # 3) bevorzugte Terme ersetzen
        for k, v in (style.preferred_terms or {}).items():
            md = re.sub(rf"\b{k}\b", v, md)

        return md

    _guardrails_cache: dict | None = None  # {"sig": str, "text": str}

    def _read_guardrail_docs(self, max_chars: int = 8000) -> str:
        """
        Read *.md/*.txt from data/thesis/guardrails, concatenate them,
        softly truncate for prompt safety, and cache by (path+mtime) signature.
        """
        try:
            files = list_guardrail_files()  # -> [absolute_pfade]
        except Exception:
            files = []

        # Nur .md / .txt
        files = [p for p in files if os.path.splitext(p)[1].lower() in {".md", ".txt"}]
        if not files:
            return ""

        # Signatur aus Pfad + mtime
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
                # Kleines Header-Label, damit das Modell die Quelle sieht
                relname = os.path.basename(p)
                parts.append(f"\n---\n# Guardrail: {relname}\n{txt}\n")
            except Exception:
                continue

        blob = "\n".join(parts).strip()

        if len(blob) > max_chars:
            lines = blob.splitlines()
            head = []
            bullets = []
            for ln in lines:
                if ln.startswith("#"):
                    head.append(ln)
                elif ln.lstrip().startswith(("-", "*", "•")):
                    bullets.append(ln)
            summarized = "\n".join(head + bullets)
            if 500 < len(summarized) < max_chars:
                blob = summarized
            else:
                blob = blob[:max_chars] + "\n… (truncated)"

        self._guardrails_cache = {"sig": sig, "text": blob}
        return blob

    # --- NEU: lockere Zielerkennung ohne vorhandene Outline ----------------------

    def _extract_target_location_loose(self, text: str) -> Optional[tuple[int, Optional[int], Optional[str]]]:
        """
        Loose extraction of (chapter, section, optional title) from free text, e.g.:
        - "4.1 Something, keywords: ..."
        - "Chapter 3.2 Federated Learning in Radiology"
        - "chapter 2 Related Work"
        Return: (chapter_index, section_index|None, extracted_title|None)
        """
        t = (text or "").strip()

        # Muster 1:  "4.1 <Titel...>"
        m = re.search(r"(?:^|\b)(\d+)(?:\.(\d+))\s+([^\n,;]+)", t, flags=re.IGNORECASE)
        if m:
            ch = int(m.group(1))
            sec = int(m.group(2))
            title = m.group(3).strip()
            # Titel bis zu "keywords:" oder "draft:" abtrennen
            title = re.split(r"\b(keywords?|draft|stichw(?:örter)?)\s*[:：]", title, flags=re.IGNORECASE)[0].strip()
            return ch, sec, title if title else None

        # Muster 2: "Kapitel 3.2 <Titel...>"
        m = re.search(r"(?:kapitel|chapter)\s+(\d+)\.(\d+)\s+([^\n,;]+)", t, flags=re.IGNORECASE)
        if m:
            ch = int(m.group(1)); sec = int(m.group(2))
            title = m.group(3).strip()
            title = re.split(r"\b(keywords?|draft|stichw(?:örter)?)\s*[:：]", title, flags=re.IGNORECASE)[0].strip()
            return ch, sec, title if title else None

        # Muster 3: "Kapitel 4 <Titel...>" oder "4.0 <Titel...>"
        m = re.search(r"(?:kapitel|chapter)\s+(\d+)\s+([^\n,;]+)", t, flags=re.IGNORECASE)
        if m:
            ch = int(m.group(1))
            title = m.group(2).strip()
            title = re.split(r"\b(keywords?|draft|stichw(?:örter)?)\s*[:：]", title, flags=re.IGNORECASE)[0].strip()
            return ch, None, title if title else None

        m = re.search(r"(?:^|\b)(\d+)\.0\s+([^\n,;]+)", t, flags=re.IGNORECASE)
        if m:
            ch = int(m.group(1))
            title = m.group(2).strip()
            title = re.split(r"\b(keywords?|draft|stichw(?:örter)?)\s*[:：]", title, flags=re.IGNORECASE)[0].strip()
            return ch, None, title if title else None

        return None
    



