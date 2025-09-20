# Data Models

## Pydantic Models

### TopicSuggestion
```python
from pydantic import BaseModel

class TopicSuggestion(BaseModel):
    title: str
    description: str
    relevance: float
```

### ResearchSummary
```python
from pydantic import BaseModel

class ResearchSummary(BaseModel):
    title: str
    authors: list[str]
    publication_year: int
    summary: str
    url: str
```

### OutlineSection
```python
from pydantic import BaseModel

class OutlineSection(BaseModel):
    title: str
    description: str
    subsections: list["OutlineSection"] = []

OutlineSection.model_rebuild()
```
