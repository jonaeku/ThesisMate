# Research & Topic Scout Agent Implementation Plan

**Created**: 2025-09-22  
**Status**: Ready for Implementation  
**Architecture**: Tool-Based Agent System

## Project Vision

Transform ThesisMate's placeholder Research and Topic Scout agents into intelligent, collaborative agents that use a tool-based architecture to help students discover relevant thesis topics and conduct comprehensive research.

## Key Requirements (From User Discussion)

1. **Free Academic APIs**: Google Scholar, arXiv, Semantic Scholar, CrossRef
2. **Conversational Interface**: All interactions should be natural, back-and-forth conversations
3. **Local JSON Storage**: Papers stored locally with links and BibTeX entries
4. **Collaborative Agents**: Topic Scout and Research Agent work together to validate topics
5. **Basic BibTeX**: Simple citation management and export functionality
6. **Tool-Based Architecture**: Agents orchestrate tools rather than implementing functionality directly

## Architecture Philosophy

**Keep It Simple**: Agents have a few simple methods that call external APIs and store data in JSON files. No complex abstractions or over-engineering.

```
Agent → Simple API calls → JSON storage
```

**Core Principle**: 
- Agents do the work directly with simple, readable methods
- Use existing libraries (requests, json) 
- Store everything in simple JSON files
- Focus on working code over complex architecture

## Agent Collaboration Flow

```
1. User: "I'm interested in AI and sustainability"
2. Topic Scout: Asks follow-up questions using ConversationTool
3. Topic Scout: For each potential topic → Research Agent validates using SearchTools
4. Research Agent: Returns topic feasibility scores using AnalysisTools
5. Topic Scout: Presents validated topics with research availability
6. User: Selects topic
7. Research Agent: Deep dive using multiple SearchTools + StorageTools
8. Both agents: Collaborate to refine topic using GapAnalysisTools
```

## Implementation Phases

### Phase 1: Simple Data Models & Storage (Day 1)
- Add a few new Pydantic models (Paper, TopicEvaluation)
- Create simple JSON file storage functions
- Basic paper deduplication

### Phase 2: Research Agent (Day 2-3)
- Add simple API calls to arXiv and Semantic Scholar
- Implement paper collection and basic scoring
- Store papers in JSON file with BibTeX

### Phase 3: Topic Scout Agent (Day 3-4)
- Simple conversational flow using OpenRouter
- Validate topics by calling Research Agent
- Store conversation state in JSON

### Phase 4: Integration (Day 4-5)
- Connect agents in orchestrator
- Test with Chainlit UI
- Simple BibTeX export function

## Success Metrics

- **Topic Scout**: Can discover 3-5 validated thesis topics through conversation
- **Research Agent**: Can collect 20+ relevant papers with gap analysis
- **Collaboration**: Agents seamlessly hand off and validate each other's work
- **User Experience**: Natural conversation flow with research-backed suggestions
- **Data Management**: Proper BibTeX export and paper organization

## Next Steps

1. Create tool specifications and interfaces
2. Implement core academic API tools
3. Build storage and analysis tools
4. Enhance agent implementations
5. Integrate with UI and test end-to-end

## Simple Implementation Approach

**What we'll actually build:**
1. Enhanced Pydantic models in existing `models.py`
2. Simple API functions in `utils/` directory
3. JSON storage functions in `utils/storage.py`
4. Enhanced agent classes that use these simple functions
5. No complex tool abstractions or interfaces

**Files to create:**
- `src/utils/storage.py` - Simple JSON storage functions
- `src/utils/academic_apis.py` - Simple API calls to arXiv, Semantic Scholar
- Enhanced `src/models/models.py` - Add Paper and TopicEvaluation models
- Enhanced agent files with actual implementations

This keeps everything simple, readable, and working while following Python best practices.
