from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Literal

class TopicSuggestion(BaseModel):
    title: str
    description: str
    relevance: float
    why_relevant: str = ""
    research_approach: str = ""
    sample_papers: List['Paper'] = []  # Forward reference
    research_validation: Optional['TopicEvaluation'] = None

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

class UserContext(BaseModel):
    field: Optional[str] = None
    interests: List[str] = []
    background: Optional[str] = None
    constraints: List[str] = []
    pending_agent: Optional[str] = None  # Agent waiting for user response
    pending_request: Optional[str] = None  # Original request that needs follow-up
    enriched_input: Optional[str] = None  # Combined original request + user response

# New dynamic communication models
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
    missing_info: List[str] = []
    reasoning: str
    suggested_questions: List[str] = []

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
    collaboration_agents: List[str] = []
    immediate_response: Optional[str] = None

# Legacy response models (for backward compatibility)
class TopicScoutResponse(BaseModel):
    success: bool
    result: Optional[List[TopicSuggestion]] = None
    needs_info: Optional[str] = None  # Was fehlt: "field", "interests", etc.
    message: Optional[str] = None  # Beschreibung was fehlt
    error_message: Optional[str] = None

OutlineSection.model_rebuild()
