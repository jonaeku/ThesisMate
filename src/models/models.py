from pydantic import BaseModel
from typing import List, Optional

class TopicSuggestion(BaseModel):
    title: str
    description: str
    relevance: float

class ResearchSummary(BaseModel):
    title: str
    authors: list[str]
    publication_year: int
    summary: str
    url: str

class OutlineSection(BaseModel):
    title: str
    description: str
    subsections: list["OutlineSection"] = []

class Paper(BaseModel):
    title: str
    authors: List[str]
    abstract: str
    url: str
    bibtex: str = ""
    year: int
    relevance_score: float = 0.0
    source: str = ""  # "arxiv", "crossref", "semantic_scholar"
    citation_count: Optional[int] = None
    doi: Optional[str] = None

class TopicEvaluation(BaseModel):
    topic: str
    paper_count: int
    feasibility_score: float
    sample_papers: List[Paper] = []
    research_gaps: List[str] = []
    confidence_score: float = 0.0

class ConversationState(BaseModel):
    field: str = ""
    interests: List[str] = []
    current_topics: List[str] = []
    conversation_history: List[str] = []
    user_background: str = ""
    preferred_methodology: str = ""

OutlineSection.model_rebuild()
