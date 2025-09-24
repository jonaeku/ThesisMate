# Agent-Tool Architektur - ThesisMate

**Datum**: 2025-09-23  
**Status**: Architektur-Vorschlag

## Grundprinzip

**Orchestrator-Ebene**: Agent-zu-Agent Kommunikation
- Orchestrator verwaltet alle Agents als gleichberechtigte Nodes
- LangGraph routing zwischen Agents

**Agent-Ebene**: Tool-Integration
- Agents können andere Agents als Tools nutzen
- Dependency Injection für benötigte Agent-Tools
- Agents bleiben testbar und modular

## Architektur-Übersicht

```
Orchestrator (LangGraph)
├── Topic Scout Agent
│   └── Research Agent (als Tool)
├── Research Agent  
├── Structure Agent
│   ├── Research Agent (als Tool)
│   └── Topic Scout Agent (als Tool)
├── Writing Agent (Draft Enhancement)
│   ├── Research Agent (als Tool)
│   └── Structure Agent (als Tool)
└── Review Agent
    └── Writing Agent (als Tool)
```

## Code-Struktur

### Orchestrator (Agent-zu-Agent)
```python
class Orchestrator:
    def __init__(self):
        # Alle Agents als eigenständige Services
        self.research_agent = ResearchAgent()
        self.topic_scout = TopicScoutAgent(research_tool=self.research_agent)
        self.structure_agent = StructureAgent(
            research_tool=self.research_agent,
            topic_tool=self.topic_scout
        )
        self.writing_agent = WritingAgent(
            research_tool=self.research_agent,
            structure_tool=self.structure_agent
        )
        
        # LangGraph für Agent-Orchestrierung
        self.graph = StateGraph(ThesisMateState)
        self.graph.add_node("topic_scout", self.topic_scout.respond)
        self.graph.add_node("research", self.research_agent.respond)
        self.graph.add_node("structure", self.structure_agent.respond)
        self.graph.add_node("writing", self.writing_agent.respond)
        
        # Routing zwischen Agents
        self.graph.add_conditional_edges("topic_scout", self.route_from_topic)
        self.graph.add_conditional_edges("research", self.route_from_research)
```

### Agent-Ebene (Tool-Integration)

#### Topic Scout Agent
```python
class TopicScoutAgent:
    def __init__(self, research_tool: ResearchAgent):
        self.research_tool = research_tool
    
    def respond(self, query: str):
        # Normale Topic Scout Logic
        topic_ideas = self.generate_topic_ideas(query)
        
        # Nutzt Research Agent als Tool für Validierung
        validated_topics = []
        for topic in topic_ideas:
            paper_count = self.research_tool.count_available_papers(topic)
            if paper_count >= 10:
                validated_topics.append(topic)
        
        return self.format_response(validated_topics)
```

#### Structure Agent
```python
class StructureAgent:
    def __init__(self, research_tool: ResearchAgent, topic_tool: TopicScoutAgent):
        self.research_tool = research_tool
        self.topic_tool = topic_tool
    
    def respond(self, query: str):
        # Nutzt Research Tool für Paper-Analyse
        papers = self.research_tool.get_papers_for_structure(query)
        
        # Nutzt Topic Tool für Themen-Verfeinerung falls nötig
        if self.needs_topic_refinement(papers):
            refined_topic = self.topic_tool.refine_topic(query, papers)
            papers = self.research_tool.get_papers_for_structure(refined_topic)
        
        return self.create_structure(papers)
```

#### Writing Agent
```python
class WritingAgent:
    def __init__(self, research_tool: ResearchAgent, structure_tool: StructureAgent):
        self.research_tool = research_tool
        self.structure_tool = structure_tool
    
    def respond(self, user_draft: str):
        # Analysiert User-Draft
        draft_analysis = self.analyze_draft(user_draft)
        
        # Nutzt Research Tool für zusätzliche Quellen zur Verbesserung
        supporting_papers = self.research_tool.find_supporting_evidence(draft_analysis.topic)
        
        # Nutzt Structure Tool für Verbesserungsvorschläge
        structure_suggestions = self.structure_tool.suggest_improvements(user_draft)
        
        return self.enhance_draft(user_draft, supporting_papers, structure_suggestions)
```

## Vorteile dieser Architektur

### Orchestrator-Ebene
- **Klare Trennung**: Orchestrator verwaltet nur Agent-Flows
- **Flexible Routing**: LangGraph ermöglicht komplexe Workflows
- **Zentrale Kontrolle**: Ein Punkt für Logging, Monitoring, Error Handling

### Agent-Ebene
- **Modulare Tools**: Agents nutzen andere Agents als spezialisierte Tools
- **Testbarkeit**: Tools können gemockt werden
- **Wiederverwendbarkeit**: Ein Agent kann von mehreren anderen genutzt werden
- **Lose Kopplung**: Dependency Injection statt harte Abhängigkeiten

## Beispiel-Workflows

### Komplexer Workflow: Draft Enhancement
```
1. User: "Verbessere meine Einleitung: [User-geschriebener Draft]"
   → Orchestrator: Route zu Writing Agent

2. Writing Agent:
   - Analysiert User-Draft
   - Nutzt Research Tool → Findet zusätzliche relevante Quellen
   - Nutzt Structure Tool → Schlägt strukturelle Verbesserungen vor
   - Erstellt enhanced Version des User-Drafts

3. Orchestrator: Route zu Review Agent für Qualitätskontrolle
```

### Einfacher Workflow: Topic Discovery
```
1. User: "Hilf mir bei Themenfindung"
   → Orchestrator: Route zu Topic Scout

2. Topic Scout:
   - Führt Conversation mit User
   - Nutzt Research Tool intern für Validierung
   - Gibt validierte Topics zurück

3. Orchestrator: Entscheidet basierend auf User-Response
```

## Implementation Strategy

### Phase 1: Basis-Architektur
- Orchestrator mit einfachem Agent-Routing
- Agents ohne Tool-Dependencies (wie aktuell)

### Phase 2: Tool-Integration
- Research Agent als Tool in Topic Scout
- Dependency Injection implementieren

### Phase 3: Erweiterte Tool-Nutzung
- Structure Agent nutzt Research + Topic Tools
- Writing Agent nutzt Research + Structure Tools

### Phase 4: Optimierung
- Caching für Tool-Aufrufe
- Performance-Monitoring
- Error-Handling für Tool-Failures

## Technische Details

### Dependency Injection
```python
# Im Orchestrator
research_agent = ResearchAgent()
topic_scout = TopicScoutAgent(research_tool=research_agent)

# Für Tests
mock_research = MockResearchAgent()
topic_scout = TopicScoutAgent(research_tool=mock_research)
```

### Tool Interface
```python
class AgentTool(ABC):
    @abstractmethod
    def execute(self, query: str, context: dict) -> dict:
        pass

class ResearchAgentTool(AgentTool):
    def __init__(self, research_agent: ResearchAgent):
        self.agent = research_agent
    
    def execute(self, query: str, context: dict) -> dict:
        return self.agent.collect_papers(query, context)
```

## Fazit

**Zwei-Ebenen-Architektur**:
1. **Orchestrator**: Agent-zu-Agent Workflows (LangGraph)
2. **Agents**: Tool-Integration für spezialisierte Funktionen

**Flexibel, testbar, erweiterbar.**
