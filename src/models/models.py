# src/models/models.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal

# ---------- Research & Topics ----------

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
    sample_papers: List[Paper] = Field(default_factory=list)
    research_gaps: List[str] = Field(default_factory=list)
    confidence_score: float = 0.0

class TopicSuggestion(BaseModel):
    title: str
    description: str
    relevance: float
    why_relevant: str = ""
    research_approach: str = ""
    sample_papers: List[Paper] = Field(default_factory=list)
    research_validation: Optional[TopicEvaluation] = None

class ResearchSummary(BaseModel):
    title: str
    authors: List[str]
    publication_year: int
    summary: str
    url: str

# ---------- Thesis Outline ----------

class OutlineSection(BaseModel):
    title: str
    description: str = ""
    subsections: List["OutlineSection"] = Field(default_factory=list)

class OutlineChapter(BaseModel):
    title: str
    sections: List[OutlineSection] = Field(default_factory=list)

class ThesisOutline(BaseModel):
    title: str
    chapters: List[OutlineChapter] = Field(default_factory=list)

# ---------- Writing Agent ----------

class WritingStyleConfig(BaseModel):
    academic_style: Literal["formal", "neutral", "concise", "narrative"] = "formal"
    voice: Literal["third_person", "first_person_plural", "impersonal"] = "impersonal"
    tense: Literal["present", "past", "mixed"] = "present"
    citation_style: Literal["APA", "MLA", "Chicago", "IEEE", "Harvard"] = "APA"
    target_readability: Literal["graduate", "undergraduate", "expert"] = "graduate"
    language: Literal["de", "en"] = "en"
    paragraph_length: Literal["short", "medium", "long"] = "medium"
    avoid_phrases: List[str] = []            # z.B. Füllwörter, Phrasen
    preferred_terms: Dict[str, str] = {}     # {"AI":"artificial intelligence"}

class GuardrailsConfig(BaseModel):
    plagiarism_check: bool = True
    require_citations_for_claims: bool = True
    disallow_first_person: bool = True
    allow_file_uploads: bool = True          # nur Metainfo; eigentliche Upload-Handling im Frontend
    max_claims_without_source: int = 0
    banned_sources: List[str] = []           # z.B. Blogs
    safe_content_rules: List[str] = []       # Zusatzregeln

class DraftPassage(BaseModel):
    chapter_index: int                       # 1-basiert
    section_index: Optional[int] = None      # 1-basiert
    title: Optional[str] = None              # Überschrift der Section, falls vorhanden
    content_markdown: str
    citations: List[str] = []                # BibTeX keys oder URLs
    notes: Optional[str] = None

# ---------- Conversation / Context ----------

class ConversationState(BaseModel):
    field: str = ""
    interests: List[str] = Field(default_factory=list)
    current_topics: List[str] = Field(default_factory=list)
    conversation_history: List[str] = Field(default_factory=list)
    user_background: str = ""
    preferred_methodology: str = ""

class UserContext(BaseModel):
    # High-level user info
    field: Optional[str] = None
    interests: List[str] = Field(default_factory=list)
    background: Optional[str] = None

    # Flexible constraints/config (z. B. {"structure_options": {...}})
    constraints: Dict[str, Any] = Field(default_factory=dict)

    # Optional working title / topic for StructureAgent
    working_title: Optional[str] = None
    topic: Optional[str] = None

    # Cross-agent scratchpad
    research_summaries: Optional[List[ResearchSummary]] = None

    # Latest outputs to surface across agents
    latest_outline: Optional[ThesisOutline] = None

    # Orchestrator control (pending Q&A)
    pending_agent: Optional[str] = None      # Agent waiting for user response
    pending_request: Optional[str] = None    # Original request that needs follow-up
    enriched_input: Optional[str] = None     # Combined original request + user response

    latest_outline: Optional["ThesisOutline"] = None
    writing_style: Optional[WritingStyleConfig] = None
    guardrails: Optional[GuardrailsConfig] = None

# ---------- Agent messaging ----------

class AgentInstruction(BaseModel):
    requesting_agent: str
    action_type: Literal["ask_user", "call_agent", "present_results", "collaborate"]
    target: str  # "user" or specific agent name
    message: str
    reasoning: str
    context_needed: Optional[Dict[str, Any]] = None
    next_steps: Optional[List[str]] = None

class AgentCapabilityAssessment(BaseModel):
    can_handle: bool
    confidence: float  # 0.0 to 1.0
    missing_info: List[str] = Field(default_factory=list)
    reasoning: str
    suggested_questions: List[str] = Field(default_factory=list)

class AgentResponse(BaseModel):
    success: bool
    agent_name: str
    result: Optional[Any] = None
    instructions: Optional[List[AgentInstruction]] = None
    needs_collaboration: Optional[Dict[str, str]] = None  # {agent_name: reason}
    user_message: Optional[str] = None
    capability_assessment: Optional[AgentCapabilityAssessment] = None
    updated_context: Optional[UserContext] = None  # Updated context to pass back to orchestrator

class RoutingDecision(BaseModel):
    primary_agent: str
    reasoning: str
    confidence: float
    requires_collaboration: bool = False
    collaboration_agents: List[str] = Field(default_factory=list)
    immediate_response: Optional[str] = None

# ---------- Legacy (compat) ----------

class TopicScoutResponse(BaseModel):
    success: bool
    result: Optional[List[TopicSuggestion]] = None
    needs_info: Optional[str] = None  # Was fehlt: "field", "interests", etc.
    message: Optional[str] = None     # Beschreibung was fehlt
    error_message: Optional[str] = None

# Forward refs
OutlineSection.model_rebuild()
TopicSuggestion.model_rebuild()
TopicEvaluation.model_rebuild()
ThesisOutline.model_rebuild()
