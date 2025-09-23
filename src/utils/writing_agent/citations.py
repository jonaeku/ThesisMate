from typing import List
from src.models.models import ResearchSummary
from .bibtex import select_cites

def from_research_summaries(summaries: List[ResearchSummary], citation_style: str, limit: int = 3) -> list[str]:
    cites = []
    for r in summaries[:limit]:
        first = r.authors[0] if r.authors else "Unknown"
        if citation_style.upper() == "APA": cites.append(f"({first}, {r.publication_year})")
        elif citation_style.upper() == "MLA": cites.append(f"({first} {r.publication_year})")
        else: cites.append(f"[{first} {r.publication_year}]")
    return cites

def combined_cites(summaries: List[ResearchSummary], citation_style: str) -> str:
    return " ".join(from_research_summaries(summaries, citation_style) + select_cites(citation_style))
