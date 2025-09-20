from pydantic import BaseModel

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

OutlineSection.model_rebuild()
