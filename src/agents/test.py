from __future__ import annotations
from typing import List, Optional, Tuple
from dataclasses import asdict

from src.models.models import (
    OutlineSection,
    ResearchSummary,
    UserContext,
    AgentResponse,
    AgentInstruction,
    AgentCapabilityAssessment,
)
from src.utils.logging import get_logger
from src.utils.openrouter_client import OpenRouterClient

logger = get_logger(__name__)


class StructureAgent:
    """
    Aufgaben:
    - Erstellt eine belastbare Thesis-Gliederung (Kapitel, Unterkapitel, logischer Flow)
    - Passt die Gliederung dynamisch an, wenn Research-Summaries dazukommen/ändern
    - Optionale GitHub-/Local-Lookups (z.B. vorhandene README/Docs oder bestehende Outline-Dateien einlesen)

    Hinweise zur Integration:
    - Spiegelbildlich zu TopicScout/Research: can_handle_request(), process_request(), respond() (legacy)
    - Nutzt OpenRouterClient für LLM-Aufgaben (Outline-Generierung und -Adaption)
    """

    def __init__(self, repo_lookup=None, local_lookup=None):
        """
        repo_lookup: Optionales Callble, das z.B. eine GitHub-Repo-URL akzeptiert und Text/Dateiliste zurückgibt.
        local_lookup: Optionales Callable, das einen lokalen Pfad akzeptiert und Text/Dateiliste zurückgibt.
        """
        self.client = OpenRouterClient()
        self.agent_name = "structure_agent"
        self.repo_lookup = repo_lookup
        self.local_lookup = local_lookup

    # ---------------------------
    # Public API (TopicScout/Research-Style)
    # ---------------------------

    def can_handle_request(self, user_input: str, context: UserContext) -> AgentCapabilityAssessment:
        """
        Einschätzung, ob der StructureAgent zuständig ist.
        """
        try:
            prompt = f"""You are a Structure Agent for thesis outlines.

Analyze if you can handle this request:

User request: "{user_input}"
Context: Field: {context.field or 'Unknown'}, Interests: {context.interests or 'None'}

You CAN handle:
- Thesis/Diss outline requests (chapters, sections, flow)
- Requests to adapt/update/improve an existing outline
- Structuring literature into chapters/subsections
- Mapping research summaries into a logical thesis structure
- (Optionally) Merging outline with GitHub/local notes

You CANNOT handle:
- Writing full content
- Deep literature search (delegate to research_agent)
- Topic discovery (delegate to topic_scout)

Respond JSON:
{{
  "can_handle": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "short reason"
}}"""

            messages = [
                {"role": "system", "content": "You decide if a request is about thesis structure/outline."},
                {"role": "user", "content": prompt},
            ]
            resp = self.client.chat_completion(messages, temperature=0.2, max_tokens=200)

            import json
            data = {"can_handle": False, "confidence": 0.5, "reasoning": "Fallback"}
            if resp:
                try:
                    data = json.loads(resp.strip())
                except Exception:
                    # Fallback: einfache Keyword-Heuristik
                    low = user_input.lower()
                    if any(k in low for k in ["outline", "structure", "gliederung", "kapitel", "chapter", "toc"]):
                        data = {"can_handle": True, "confidence": 0.7, "reasoning": "Keyword match for structure"}
            return AgentCapabilityAssessment(
                can_handle=bool(data.get("can_handle")),
                confidence=float(data.get("confidence", 0.6)),
                missing_info=[],
                reasoning=data.get("reasoning", "Assessment complete"),
                suggested_questions=[],
            )
        except Exception as e:
            logger.error(f"[StructureAgent] Error in can_handle_request: {e}")
            return AgentCapabilityAssessment(
                can_handle=False, confidence=0.0, reasoning=f"Error during assessment: {e}"
            )

    def process_request(
        self,
        user_input: str,
        context: UserContext,
        research_summaries: Optional[List[ResearchSummary]] = None,
        options: Optional[dict] = None,
    ) -> AgentResponse:
        """
        Hauptlogik:
        - Prüfen, ob zuständig
        - Prüfen, ob genug Infos vorliegen (Topic/Arbeitstitel; optional Summaries)
        - Outline generieren/aktualisieren
        - Optional: GitHub/Local-Material einmischen
        """
        logger.info(f"[StructureAgent] processing: {user_input}")
        try:
            assessment = self.can_handle_request(user_input, context)
            if not assessment.can_handle:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    capability_assessment=assessment,
                    user_message="Das klingt nicht nach Gliederung. Übergabe an den Orchestrator.",
                )

            # Relevante Informationen extrahieren
            topic = self._extract_topic_for_outline(user_input, context)

            # Haben wir genug, um eine Outline zu bauen?
            if not topic:
                question = "Für die Gliederung brauche ich einen (Arbeits-)Titel oder ein klares Thema. Wie lautet dein Thema?"
                instruction = AgentInstruction(
                    requesting_agent=self.agent_name,
                    action_type="ask_user",
                    target="user",
                    message=question,
                    reasoning="Ohne Thema/Arbeitstitel ist keine sinnvolle Gliederung möglich.",
                )
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    instructions=[instruction],
                    user_message=question,
                )

            # Optional Material einlesen (GitHub/Local)
            external_notes = self._optional_material_lookup(options or {})

            # Outline generieren/aktualisieren (LLM nutzt Research-Summaries + Notizen falls vorhanden)
            outline = self._generate_or_adapt_outline(topic, research_summaries or [], external_notes)

            # Schön formatiert für User
            msg = self._format_outline_for_user(outline, topic)

            return AgentResponse(
                success=True,
                agent_name=self.agent_name,
                result=outline,
                user_message=msg,
            )
        except Exception as e:
            logger.error(f"[StructureAgent] process_request error: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                user_message=f"Fehler bei der Outline-Erstellung: {str(e)}",
            )

    # ---------------------------
    # Legacy API (Kompatibilität)
    # ---------------------------
    def respond(self, topic: str, research_summaries: List[ResearchSummary]) -> OutlineSection:
        """
        Alte Signatur – liefert direkt eine OutlineSection zurück.
        """
        try:
            outline = self._generate_or_adapt_outline(topic, research_summaries or [], external_notes=None)
            return outline
        except Exception as e:
            logger.error(f"[StructureAgent] legacy respond error: {e}")
            # Minimalfallback
            return OutlineSection(
                title="Thesis Outline",
                description=f"A proposed outline for the thesis on '{topic}'.",
                subsections=[
                    OutlineSection(title="Introduction", description="Introduce the topic and research question."),
                    OutlineSection(title="Related Work", description="Synthesize relevant literature."),
                    OutlineSection(title="Methodology", description="Detail methods, data, and procedures."),
                    OutlineSection(title="Experiments / Results", description="Present findings."),
                    OutlineSection(title="Discussion", description="Interpret results, limitations."),
                    OutlineSection(title="Conclusion & Future Work", description="Summarize and propose next steps."),
                ],
            )

    # ---------------------------
    # Internals
    # ---------------------------
    def _extract_topic_for_outline(self, user_input: str, context: UserContext) -> Optional[str]:
        """
        Versucht, einen Arbeitstitel/Topic aus Input+Context zu extrahieren.
        """
        # 1) Wenn der User explizit einen Titel/Topic schreibt, LLM-extrahieren
        try:
            prompt = f"""Extract a concise thesis working title from the following content.
If no clear title exists, answer EXACTLY with "NONE".

User input: "{user_input}"
Field: {context.field or 'Unknown'}
Interests: {', '.join(context.interests) if context.interests else 'None'}

Title:"""
            messages = [
                {"role": "system", "content": "Extract short working titles (max ~12 words)."},
                {"role": "user", "content": prompt},
            ]
            resp = self.client.chat_completion(messages, temperature=0.2, max_tokens=40)
            if resp and resp.strip() and resp.strip().upper() != "NONE":
                return resp.strip().strip('"').strip()
        except Exception as e:
            logger.warning(f"[StructureAgent] Title extraction failed, fallback: {e}")

        # 2) Fallback: Verwende Field + Interests
        if context.field and context.interests:
            return f"{context.field}: {', '.join(context.interests[:2])}"
        return None

    def _optional_material_lookup(self, options: dict) -> Optional[str]:
        """
        Liest optionales Material aus GitHub/Local, wenn übergeben.
        options = {"github_url": str, "local_path": str, "include": ["README.md","/docs/outline.md", ...]}
        Rückgabe: konsolidierter Text (oder None)
        """
        notes = []
        try:
            gh = options.get("github_url")
            lp = options.get("local_path")
            includes = options.get("include") or []

            if gh and self.repo_lookup:
                try:
                    txt = self.repo_lookup(gh, includes=includes)
                    if txt:
                        notes.append(txt if isinstance(txt, str) else "\n".join(txt))
                except Exception as e:
                    logger.warning(f"[StructureAgent] repo_lookup failed: {e}")

            if lp and self.local_lookup:
                try:
                    txt = self.local_lookup(lp, includes=includes)
                    if txt:
                        notes.append(txt if isinstance(txt, str) else "\n".join(txt))
                except Exception as e:
                    logger.warning(f"[StructureAgent] local_lookup failed: {e}")

            return "\n\n".join([n for n in notes if n]) if notes else None
        except Exception as e:
            logger.warning(f"[StructureAgent] optional_material_lookup error: {e}")
            return None

    def _generate_or_adapt_outline(
        self,
        topic: str,
        research_summaries: List[ResearchSummary],
        external_notes: Optional[str],
    ) -> OutlineSection:
        """
        LLM-gestützte Outline-Generierung/-Adaption.
        """
        # Baue eine kompakte Liste von Papers/Findings
        papers_block = ""
        if research_summaries:
            lines = []
            for i, rs in enumerate(research_summaries[:10], 1):
                line = f"{i}. {rs.title} ({rs.publication_year}) — {', '.join(rs.authors[:3]) if rs.authors else ''}\n   {rs.summary[:220]+'...' if rs.summary and len(rs.summary)>220 else (rs.summary or '')}"
                lines.append(line)
            papers_block = "\n".join(lines)

        notes_block = external_notes[:2000] + "..." if external_notes and len(external_notes) > 2000 else (external_notes or "")

        prompt = f"""You are an expert thesis architect. Design a rigorous, logically flowing thesis outline.

Working title/topic: "{topic}"

Incorporate (if helpful) these research notes/papers:
{papers_block if papers_block else "(no papers provided)"}

Also consider these external notes if present (optional):
{notes_block if notes_block else "(none)"}

REQUIREMENTS:
- 6–8 top-level chapters max.
- Each chapter has 2–5 subsections.
- Logical flow: (1) Motivation → (2) Background/Literature → (3) Method(s) → (4) Experiments/Results → (5) Discussion → (6) Conclusion/Future Work (adapt as needed).
- Be specific in subsection names (avoid 'misc').
- Return ONLY as Markdown headings with levels:
# Chapter Title
## 1.1 Subsection
## 1.2 Subsection
# Next Chapter
## 2.1 ...
(Do NOT include explanations outside headings.)"""

        messages = [
            {"role": "system", "content": "Return only Markdown headings (#, ##). No extra prose."},
            {"role": "user", "content": prompt},
        ]

        resp = self.client.chat_completion(messages, temperature=0.5, max_tokens=1800)
        if not resp or not resp.strip():
            # Minimalfallback
            return OutlineSection(
                title="Thesis Outline",
                description=f"Initial outline for '{topic}' (fallback).",
                subsections=[
                    OutlineSection(title="1. Introduction", description="Motivation, problem statement, contributions"),
                    OutlineSection(title="2. Background & Related Work", description="Key concepts and literature synthesis"),
                    OutlineSection(title="3. Methodology", description="Approach, data, implementation details"),
                    OutlineSection(title="4. Experiments & Results", description="Design, metrics, results"),
                    OutlineSection(title="5. Discussion", description="Interpretation, limitations, threats to validity"),
                    OutlineSection(title="6. Conclusion & Future Work", description="Summary and future directions"),
                ],
            )

        return self._parse_markdown_headings_to_outline(topic, resp)

    def _parse_markdown_headings_to_outline(self, topic: str, md: str) -> OutlineSection:
        """
        Sehr robuste, einfache Parser-Logik:
        - # ...  → Kapitel (OutlineSection)
        - ## ... → Unterkapitel (OutlineSection unter letztem Kapitel)
        - Ignoriert andere Levels bewusst (kann man leicht erweitern)
        """
        import re

        lines = [l.strip() for l in md.splitlines() if l.strip()]
        chapters: List[OutlineSection] = []
        current: Optional[OutlineSection] = None

        h1 = re.compile(r"^#\s+(.*)")
        h2 = re.compile(r"^##\s+(.*)")

        for line in lines:
            m1 = h1.match(line)
            m2 = h2.match(line)
            if m1:
                # neues Kapitel
                if current:
                    chapters.append(current)
                current = OutlineSection(title=m1.group(1).strip(), description="", subsections=[])
            elif m2 and current:
                current.subsections.append(OutlineSection(title=m2.group(1).strip(), description=""))
            else:
                # andere Zeilen ignorieren (gemäß Vorgabe)
                pass

        if current:
            chapters.append(current)

        return OutlineSection(
            title="Thesis Outline",
            description=f"Auto-generated outline for '{topic}'.",
            subsections=chapters,
        )

    def _format_outline_for_user(self, outline: OutlineSection, topic: str) -> str:
        """
        Menschliche Darstellung als Text (für Chat-Ausgabe).
        """
        def render(sec: OutlineSection, level: int = 0) -> List[str]:
            bullet = "•" if level == 0 else "-"
            lines = [f"{'  '*level}{bullet} {sec.title}"]
            for ss in (sec.subsections or []):
                lines.extend(render(ss, level + 1))
            return lines

        lines = [f"🧭 **Outline für:** *{topic}*\n"]
        for ch in outline.subsections or []:
            lines.extend(render(ch, 0))
        lines.append("\nWenn du magst, kann ich Kapitel aufbohren (Ziele, Deliverables, Quellen) oder die Outline an neue Research-Ergebnisse anpassen.")
        return "\n".join(lines)
