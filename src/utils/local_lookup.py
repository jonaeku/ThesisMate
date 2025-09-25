# src/services/lookup.py
from __future__ import annotations
from pathlib import Path
from typing import Iterable, List
from src.models.models import ResearchSummary

class LocalThesisLookup:
    def __init__(self, root: str, exts: Iterable[str] = (".md", ".tex", ".txt", ".pdf")):
        self.root = Path(root)
        self.exts = {e.lower() for e in exts}

    def search(self, topic: str, limit: int = 5) -> List[ResearchSummary]:
        if not self.root.exists():
            return []

        results: List[ResearchSummary] = []
        topic_l = topic.lower()

        for p in self.root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in self.exts:
                continue

            # sehr schneller Heuristik-Check: Dateiname oder (für Textdateien) Inhalt enthält Topic
            stem = p.stem.lower().replace("_", " ")
            matched = topic_l in stem
            text_preview = ""

            if not matched and p.suffix.lower() in {".md", ".txt", ".tex"}:
                try:
                    txt = p.read_text(encoding="utf-8", errors="ignore")
                    matched = topic_l in txt.lower()
                    if matched:
                        # kurzer Vorschau-Text (max. 200 Zeichen)
                        text_preview = txt.strip().replace("\n", " ")[:200]
                except Exception:
                    pass

            if matched:
                results.append(
                    ResearchSummary(
                        title=p.stem + " (Local)",
                        authors=["Local File"],
                        publication_year=Path.stat(p).st_mtime_ns and 2025,  # neutral; passe später an
                        summary=text_preview or f"Local file matched for topic '{topic}'.",
                        url=str(p.resolve()),
                    )
                )
                if len(results) >= limit:
                    break

        return results
