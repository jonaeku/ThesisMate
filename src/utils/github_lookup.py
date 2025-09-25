# src/services/github_lookup.py
from __future__ import annotations
import os
from typing import List, Optional
import requests
from src.models.models import ResearchSummary

class GitHubLookup:
    API_BASE = "https://api.github.com"

    def __init__(
        self,
        owner: str,
        repo: str,
        path: str = "",
        ref: str = "HEAD",
        token: Optional[str] = None,
        text_exts: tuple[str, ...] = (".md", ".tex", ".txt"),
        name_exts: tuple[str, ...] = (".md", ".tex", ".txt", ".pdf"),
        timeout: float = 15.0,
    ):
        self.owner = owner
        self.repo = repo
        self.path = path.strip("/")
        self.ref = ref
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.text_exts = text_exts
        self.name_exts = name_exts
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "User-Agent": "ThesisMate/1.0"
        })
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})

    # ---------- public ----------

    def search(self, topic: str, limit: int = 5) -> List[ResearchSummary]:
        """
        Sucht nach Dateien im Repo, die das Topic im Namen oder (bei Textdateien) im Inhalt enthalten.
        Gibt eine Liste von ResearchSummary zurück.
        """
        topic_l = topic.lower()
        results: List[ResearchSummary] = []

        for file in self._iter_files_recursive(self.path):
            fname = file["name"]
            fpath = file["path"]
            html_url = self._make_github_url(fpath)
            ext = os.path.splitext(fname)[1].lower()

            if ext not in self.name_exts:
                continue

            matched = topic_l in fname.lower()
            preview = ""

            if not matched and ext in self.text_exts:
                text = self._download_text(file)
                if text and topic_l in text.lower():
                    matched = True
                    preview = text.strip().replace("\n", " ")[:200]

            if matched:
                results.append(
                    ResearchSummary(
                        title=os.path.splitext(fname)[0] + " (GitHub)",
                        authors=["GitHub File"],
                        publication_year=2025,  # neutraler Platzhalter
                        summary=preview or f"GitHub file matched for topic '{topic}'.",
                        url=html_url,
                    )
                )
                if len(results) >= limit:
                    break

        return results

    # ---------- intern ----------

    def _iter_files_recursive(self, path: str):
        """holt alle Dateien rekursiv via GitHub-API /contents"""
        url = f"{self.API_BASE}/repos/{self.owner}/{self.repo}/contents/{path}"
        params = {"ref": self.ref}
        r = self.session.get(url, params=params, timeout=self.timeout)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        items = r.json()
        if isinstance(items, dict):
            items = [items]

        for it in items:
            if it.get("type") == "file":
                yield it
            elif it.get("type") == "dir":
                yield from self._iter_files_recursive(it["path"])

    def _download_text(self, file: dict) -> Optional[str]:
        """lädt Text-Dateien über download_url"""
        url = file.get("download_url")
        if not url:
            return None
        r = self.session.get(url, timeout=self.timeout)
        if not r.ok:
            return None
        ctype = r.headers.get("Content-Type", "")
        if "text" in ctype or "markdown" in ctype:
            try:
                return r.text
            except Exception:
                return None
        return None

    def _make_github_url(self, path: str) -> str:
        ref = self.ref if self.ref != "HEAD" else "main"
        return f"https://github.com/{self.owner}/{self.repo}/blob/{ref}/{path}"
