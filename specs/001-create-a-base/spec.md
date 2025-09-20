# Feature Specification: Base Project for Thesis Agents

**Feature Branch**: `001-create-a-base`
**Created**: 2025-09-20
**Status**: Draft
**Input**: User description: "Create a base project for a multi-agent system called "Thesis Agents" with Pydantic integrated for data validation. Agents & Roles: - Topic Scout Agent: suggests thesis topics, returns list of TopicSuggestion (Pydantic model). - Research Agent: collects papers, returns list of ResearchSummary (Pydantic model). - Structure Agent: proposes thesis outlines, uses OutlineSection (Pydantic model). - Writing Assistant Agent: drafts sections based on summaries and outline. - Reviewer Agent: gives feedback like a supervisor. - Project Manager Agent (Orchestrator): coordinates agents and tracks deadlines. Primary Dependencies: - uv (package manager) - LangGraph (agent orchestration) - Chainlit (UI) - LangChain (LLM integration) - OpenRouter (model provider) - Pydantic (data validation) Constraints: - Keep the structure lean and clear. - Focus on skeleton code, no full implementations yet. - Must allow quick onboarding for new team members."

## User Scenarios & Testing *(mandatory)*

### Primary User Story
As a student, I want to use the Thesis Agents system to help me research and write my thesis, from finding a topic to getting feedback on my drafts.

### Acceptance Scenarios
1.  **Given** a student has a general area of interest, **When** they use the Topic Scout Agent, **Then** they receive a list of potential thesis topics.
2.  **Given** a student has a chosen topic, **When** they use the Research Agent, **Then** they receive a list of relevant research papers and summaries.
3.  **Given** a student has a collection of research, **When** they use the Structure Agent, **Then** they receive a proposed thesis outline.
4.  **Given** a student has an outline and research, **When** they use the Writing Assistant Agent, **Then** they receive a drafted section of their thesis.
5.  **Given** a student has a drafted section, **When** they use the Reviewer Agent, **Then** they receive feedback and suggestions for improvement.

### Edge Cases
- What happens when no topics are found for a given interest?
- How does the system handle a lack of research papers for a specific topic?
- What if the generated outline is not logical?

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: The system MUST provide a Topic Scout Agent that suggests thesis topics.
- **FR-002**: The Topic Scout Agent MUST return a list of `TopicSuggestion` Pydantic models.
- **FR-003**: The system MUST provide a Research Agent that collects research papers.
- **FR-004**: The Research Agent MUST return a list of `ResearchSummary` Pydantic models.
- **FR-005**: The system MUST provide a Structure Agent that proposes thesis outlines.
- **FR-006**: The Structure Agent MUST use the `OutlineSection` Pydantic model.
- **FR-007**: The system MUST provide a Writing Assistant Agent that drafts thesis sections.
- **FR-008**: The system MUST provide a Reviewer Agent that provides feedback on drafts.
- **FR-009**: The system MUST have a Project Manager Agent that orchestrates the other agents.
- **FR-010**: The system MUST use `uv` for package management.
- **FR-011**: The system MUST use `LangGraph` for agent orchestration.
- **FR-012**: The system MUST use `Chainlit` for the user interface.
- **FR-013**: The system MUST use `LangChain` for LLM integration.
- **FR-014**: The system MUST use `OpenRouter` as the model provider.
- **FR-015**: The system MUST use `Pydantic` for data validation.

### Key Entities *(include if feature involves data)*
- **TopicSuggestion**: Represents a potential thesis topic.
- **ResearchSummary**: Represents a summary of a research paper.
- **OutlineSection**: Represents a section of the thesis outline.
