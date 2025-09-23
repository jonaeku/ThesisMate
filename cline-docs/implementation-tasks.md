# Implementation Tasks - Research & Topic Scout Agents

**Simple, step-by-step tasks to build working agents**

## Phase 1: Foundation (Day 1)

### Task 1.1: Enhance Data Models
- [ ] Add `Paper` model to `src/models/models.py`
- [ ] Add `TopicEvaluation` model to `src/models/models.py`
- [ ] Add `ConversationState` model to `src/models/models.py`

### Task 1.2: Create Storage Functions
- [ ] Create `src/utils/storage.py`
- [ ] Implement `save_papers()` function
- [ ] Implement `load_papers()` function
- [ ] Implement `save_conversation_state()` function
- [ ] Implement `export_bibtex()` function
- [ ] Create `data/` directory for JSON files

### Task 1.3: Create Academic API Functions
- [ ] Create `src/utils/academic_apis.py`
- [ ] Implement `search_arxiv()` function
- [ ] Implement `search_semantic_scholar()` function
- [ ] Implement `generate_bibtex()` function
- [ ] Test API calls with simple queries

## Phase 2: Research Agent (Day 2-3)

### Task 2.1: Enhance Research Agent
- [ ] Update `src/agents/research.py`
- [ ] Implement `collect_papers()` method
- [ ] Implement `evaluate_topic()` method
- [ ] Implement `deep_research()` method
- [ ] Add paper deduplication logic
- [ ] Add basic relevance scoring

### Task 2.2: Test Research Agent
- [ ] Test with sample topics
- [ ] Verify paper collection works
- [ ] Check JSON storage works
- [ ] Test BibTeX generation

## Phase 3: Topic Scout Agent (Day 3-4)

### Task 3.1: Enhance Topic Scout Agent
- [ ] Update `src/agents/topic_scout.py`
- [ ] Implement conversation state management
- [ ] Implement `ask_next_question()` method
- [ ] Implement `suggest_topics()` method
- [ ] Add topic validation using Research Agent

### Task 3.2: Test Topic Scout Agent
- [ ] Test conversation flow
- [ ] Verify topic suggestions work
- [ ] Check collaboration with Research Agent
- [ ] Test conversation state persistence

## Phase 4: Integration (Day 4-5)

### Task 4.1: Update Orchestrator
- [ ] Update `src/orchestrator/orchestrator.py`
- [ ] Connect Research and Topic Scout agents
- [ ] Implement proper agent collaboration
- [ ] Add conversation flow management

### Task 4.2: Test Full System
- [ ] Test end-to-end conversation
- [ ] Verify paper collection and storage
- [ ] Test BibTeX export
- [ ] Check Chainlit UI integration

### Task 4.3: Final Polish
- [ ] Add error handling
- [ ] Improve user messages
- [ ] Add logging
- [ ] Create simple documentation

## Success Criteria

**Research Agent:**
- Can search arXiv and Semantic Scholar
- Collects and stores papers in JSON
- Generates BibTeX entries
- Provides topic feasibility scores

**Topic Scout Agent:**
- Conducts natural conversation
- Asks relevant follow-up questions
- Suggests validated topics
- Maintains conversation state

**Integration:**
- Agents work together seamlessly
- Conversation flows naturally in Chainlit
- Data persists between sessions
- BibTeX export works

## Quick Start Commands

```bash
# Test Research Agent
python -c "from src.agents.research import ResearchAgent; agent = ResearchAgent(); print(agent.evaluate_topic('machine learning'))"

# Test Topic Scout Agent
python -c "from src.agents.topic_scout import TopicScoutAgent; from src.agents.research import ResearchAgent; scout = TopicScoutAgent(ResearchAgent()); print(scout.ask_next_question('I like AI', None))"

# Run full system
python main.py
```

This breakdown makes it easy to implement one piece at a time and test as you go.
