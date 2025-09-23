# Simple Implementation Guide

**Goal**: Build working Research & Topic Scout agents with minimal complexity

## What We'll Actually Build

### 1. Enhanced Models (src/models/models.py)
```python
class Paper(BaseModel):
    title: str
    authors: list[str]
    abstract: str
    url: str
    bibtex: str
    year: int
    relevance_score: float = 0.0

class TopicEvaluation(BaseModel):
    topic: str
    paper_count: int
    feasibility_score: float
    sample_papers: list[Paper]

class ConversationState(BaseModel):
    field: str = ""
    interests: list[str] = []
    current_topics: list[str] = []
```

### 2. Simple Storage (src/utils/storage.py)
```python
def save_papers(papers: list[Paper], filename: str = "data/papers.json"):
    # Simple JSON save

def load_papers(filename: str = "data/papers.json") -> list[Paper]:
    # Simple JSON load

def save_conversation_state(state: ConversationState):
    # Save user's conversation progress

def export_bibtex(papers: list[Paper]) -> str:
    # Generate BibTeX string
```

### 3. Academic APIs (src/utils/academic_apis.py)
```python
def search_arxiv(query: str, max_results: int = 20) -> list[Paper]:
    # Simple arXiv API call using requests

def search_semantic_scholar(query: str, max_results: int = 20) -> list[Paper]:
    # Simple Semantic Scholar API call

def generate_bibtex(paper: Paper) -> str:
    # Generate BibTeX entry from paper data
```

### 4. Enhanced Research Agent (src/agents/research.py)
```python
class ResearchAgent:
    def collect_papers(self, topic: str) -> list[Paper]:
        # Call APIs, combine results, deduplicate
        
    def evaluate_topic(self, topic: str) -> TopicEvaluation:
        # Quick search to validate topic feasibility
        
    def deep_research(self, topic: str) -> dict:
        # Comprehensive research with gap analysis
```

### 5. Enhanced Topic Scout Agent (src/agents/topic_scout.py)
```python
class TopicScoutAgent:
    def __init__(self, research_agent: ResearchAgent):
        self.research_agent = research_agent
        
    def ask_next_question(self, user_input: str, state: ConversationState) -> str:
        # Generate next question based on conversation
        
    def suggest_topics(self, state: ConversationState) -> list[TopicEvaluation]:
        # Generate and validate topic suggestions
```

## Implementation Order

1. **Day 1**: Add models, create storage.py, create academic_apis.py
2. **Day 2**: Implement ResearchAgent with real API calls
3. **Day 3**: Implement TopicScoutAgent with conversation flow
4. **Day 4**: Connect everything in orchestrator
5. **Day 5**: Test and refine

## Key Principles

- **No abstractions**: Direct API calls, simple functions
- **Readable code**: Clear variable names, simple logic
- **Working first**: Get it working, then optimize
- **JSON everything**: Simple file-based storage
- **Minimal dependencies**: Use what's already in pyproject.toml

This approach will give you working agents in a few days without overengineering.
