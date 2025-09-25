from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import END, StateGraph
from typing import TypedDict, Annotated
import operator

from src.agents.research import ResearchAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.structure import StructureAgent
from src.agents.topic_scout import TopicScoutAgent
from src.agents.writing import WritingAssistantAgent
from src.models.models import UserContext

from src.utils.custom_logging import get_logger
from src.utils.openrouter_client import OpenRouterClient

logger = get_logger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    user_id: str
    context: UserContext
    next_agent: str


class Orchestrator:
    def __init__(self):
        self.client = OpenRouterClient()

        # Initialize agents
        self.research_agent = ResearchAgent()
        self.topic_scout = TopicScoutAgent(research_tool=self.research_agent)
        self.structure_agent = StructureAgent()
        self.writing_assistant = WritingAssistantAgent()
        self.reviewer_agent = ReviewerAgent()

        # User context storage
        self.user_contexts = {}

        # Build supervisor graph
        self._build_graph()

    def _build_graph(self):
        """Build supervisor multi-agent graph following LangGraph patterns"""
        self.graph = StateGraph(AgentState)

        # Add supervisor and agent nodes
        self.graph.add_node("supervisor", self._supervisor_node)
        self.graph.add_node("topic_scout", self._topic_scout_node)
        self.graph.add_node("research_agent", self._research_agent_node)
        self.graph.add_node("structure_agent", self._structure_agent_node)
        self.graph.add_node("writing_assistant", self._writing_assistant_node)
        self.graph.add_node("reviewer_agent", self._reviewer_agent_node)

        # Supervisor decides which agent to call
        self.graph.add_conditional_edges(
            "supervisor",
            self._supervisor_decision,
            {
                "topic_scout": "topic_scout",
                "research_agent": "research_agent",
                "structure_agent": "structure_agent",
                "writing_assistant": "writing_assistant",
                "reviewer_agent": "reviewer_agent",
                "END": END
            }
        )

        # All agents return to supervisor
        self.graph.add_edge("topic_scout", "supervisor")
        self.graph.add_edge("research_agent", "supervisor")
        self.graph.add_edge("structure_agent", "supervisor")
        self.graph.add_edge("writing_assistant", "supervisor")
        self.graph.add_edge("reviewer_agent", "supervisor")

        self.graph.set_entry_point("supervisor")
        self.runnable = self.graph.compile()

    def run(self, query: str, user_id: str = "default") -> str:
        """Main orchestration method"""
        try:
            # Get or create user context
            context = self.user_contexts.get(user_id, UserContext())

            # Initialize state
            initial_state = {
                "messages": [HumanMessage(content=query)],
                "user_id": user_id,
                "context": context,
                "next_agent": ""
            }

            # Run the graph
            result = self.runnable.invoke(initial_state)

            # Save updated context
            if "context" in result:
                self.user_contexts[user_id] = result["context"]

            # Extract final response
            if result and "messages" in result and len(result["messages"]) > 0:
                last_message = result["messages"][-1]
                return last_message.content if hasattr(last_message, 'content') else str(last_message)
            else:
                return "I couldn't generate a response. Please try again."

        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            return f"An error occurred: {str(e)}"

    def _supervisor_node(self, state: AgentState):
        """Supervisor decides which agent to call next using LLM-based routing"""
        try:
            messages = state["messages"]
            context = state["context"]

            # Handle pending agent responses
            if hasattr(context, 'pending_agent') and context.pending_agent and len(messages) > 1:
                logger.info("Agent asked question, ending conversation to wait for user response")
                return {"next_agent": "END"}

            # Use LLM to determine next action
            decision = self._make_routing_decision(messages, context)

            logger.info(f"Supervisor routing decision: {decision}")
            return {"next_agent": decision}

        except Exception as e:
            logger.error(f"Error in supervisor: {e}")
            return {
                "next_agent": "END",
                "messages": [AIMessage(content=f"I encountered an error: {str(e)}")]
            }

    def _make_routing_decision(self, messages: list[BaseMessage], context: UserContext) -> str:
        """Use LLM to make all routing decisions - both agent selection and completion detection"""
        try:
            # Extract conversation context
            conversation_history = "\n".join([
                f"{'User' if isinstance(msg, HumanMessage) else 'Assistant'}: {msg.content}"
                for msg in messages[-3:] if hasattr(msg, 'content')  # Last 3 messages for context
            ])

            current_user_input = ""
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg, HumanMessage):
                    current_user_input = last_msg.content
                elif len(messages) > 1 and isinstance(messages[-2], HumanMessage):
                    current_user_input = messages[-2].content

            # Handle pending agent
            if hasattr(context, 'pending_agent') and context.pending_agent:
                logger.info(f"Routing back to pending agent: {context.pending_agent}")

                # Enrich input for pending agent
                if hasattr(context, 'pending_request') and context.pending_request:
                    enriched_input = f"Original request: {context.pending_request}\nUser's additional info: {current_user_input}"
                    context.enriched_input = enriched_input

                # Clear pending state
                pending_agent = context.pending_agent
                context.pending_agent = None
                context.pending_request = None
                return pending_agent

            # Build comprehensive prompt for LLM decision making
            prompt = f"""You are a supervisor for a thesis writing assistant system. Analyze the conversation and decide the next action.

STEP 1: ANALYZE THE CONVERSATION CONTEXT
{conversation_history}

STEP 2: REVIEW USER CONTEXT
- Field: {context.field or 'Unknown'}
- Interests: {context.interests or 'None'}
- Has outline: {bool(getattr(context, 'latest_outline', None))}

STEP 3: UNDERSTAND AVAILABLE AGENTS
- topic_scout: Finds thesis topics, research areas, handles field/interest setup
- research_agent: Searches academic papers, literature analysis
- structure_agent: Creates thesis outlines and structure
- writing_assistant: Helps with writing content, drafting, style commands
- reviewer_agent: Reviews and provides feedback on content

STEP 4: APPLY DECISION RULES
1. If the last assistant message contains completed results (research findings, outlines, written content, reviews), respond with "END"
2. If user is asking a new question or making a new request, choose the appropriate agent
3. Route based on user intent:
   - Topic suggestions, research areas, field setup → topic_scout
   - Paper search, literature analysis → research_agent
   - Thesis structure, outlines → structure_agent
   - Writing, drafting, style commands → writing_assistant
   - Review, feedback requests → reviewer_agent
4. IMPORTANT: If you see repetitive patterns or if an agent has already provided a complete response, respond with "END" to avoid loops

STEP 5: MAKE YOUR DECISION
Based on the analysis above, respond with ONLY one word: either an agent name (e.g., "topic_scout") or "END"."""

            messages_for_llm = [
                {"role": "system", "content": "You are a routing supervisor. Respond with only one word: an agent name or 'END'. Prefer 'END' when tasks are completed to avoid loops."},
                {"role": "user", "content": prompt}
            ]

            response = self.client.chat_completion(messages_for_llm, temperature=0.1, max_tokens=20)

            if response:
                decision = response.strip().upper()
                valid_choices = ["TOPIC_SCOUT", "RESEARCH_AGENT", "STRUCTURE_AGENT", "WRITING_ASSISTANT", "REVIEWER_AGENT", "END"]

                if decision in valid_choices:
                    return decision.lower() if decision != "END" else "END"

            # Fallback - default to topic_scout for new conversations
            logger.warning(f"LLM routing failed, using fallback. Response was: {response}")
            return "topic_scout"

        except Exception as e:
            logger.error(f"Routing decision failed: {e}")
            return "topic_scout"  # Safe fallback

    def _supervisor_decision(self, state: AgentState) -> str:
        """Return the next agent to call"""
        return state["next_agent"]

    # Agent nodes - each processes with their respective agent
    def _topic_scout_node(self, state: AgentState):
        """Topic Scout agent node"""
        try:
            messages = state["messages"]
            last_message = messages[-1].content if messages else ""
            context = state["context"]

            input_to_process = self._get_input_to_process(last_message, context)

            if hasattr(self.topic_scout, 'process_request'):
                response = self.topic_scout.process_request(input_to_process, context)
                return self._handle_agent_response(response, context, "topic_scout", input_to_process)
            else:
                response_text = self.topic_scout.respond(input_to_process)
                return {"messages": [AIMessage(content=response_text)]}

        except Exception as e:
            logger.error(f"Error in topic scout: {e}")
            return {"messages": [AIMessage(content=f"Topic Scout encountered an error: {str(e)}")]}

    def _research_agent_node(self, state: AgentState):
        """Research agent node"""
        try:
            messages = state["messages"]
            last_message = messages[-1].content if messages else ""
            context = state["context"]

            input_to_process = self._get_input_to_process(last_message, context)

            if hasattr(self.research_agent, 'process_request'):
                response = self.research_agent.process_request(input_to_process, context)

                # Store research summaries if available
                self._store_research_summaries(response, context)

                return self._handle_agent_response(response, context, "research_agent", input_to_process)
            else:
                response_text = self.research_agent.respond(input_to_process)
                return {"messages": [AIMessage(content=str(response_text))]}

        except Exception as e:
            logger.error(f"Error in research agent: {e}")
            return {"messages": [AIMessage(content=f"Research Agent encountered an error: {str(e)}")]}

    def _structure_agent_node(self, state: AgentState):
        """Structure agent node"""
        try:
            messages = state["messages"]
            last_message = messages[-1].content if messages else ""
            context = state["context"]

            input_to_process = self._get_input_to_process(last_message, context)

            options = {}
            if hasattr(context, "constraints") and isinstance(context.constraints, dict):
                options = context.constraints.get("structure_options") or {}

            research_summaries = getattr(context, "research_summaries", None)

            if hasattr(self.structure_agent, "process_request"):
                response = self.structure_agent.process_request(
                    input_to_process, context,
                    research_summaries=research_summaries,
                    options=options
                )

                # Store outline if successful
                if response.success and hasattr(response, 'result'):
                    try:
                        context.latest_outline = response.result
                    except Exception as e:
                        logger.warning(f"Could not set latest_outline: {e}")

                return self._handle_agent_response(response, context, "structure_agent", input_to_process)
            else:
                # Fallback for legacy interface
                return {"messages": [AIMessage(content="Structure agent needs updating to new interface.")], "context": context}

        except Exception as e:
            logger.error(f"Error in structure agent: {e}")
            return {"messages": [AIMessage(content=f"Structure Agent encountered an error: {str(e)}")]}

    def _writing_assistant_node(self, state: AgentState):
        """Writing assistant node"""
        try:
            messages = state["messages"]
            context = state["context"]

            # Get last human message for writing assistant
            last_human = ""
            for m in reversed(messages):
                if isinstance(m, HumanMessage):
                    last_human = m.content
                    break

            input_to_process = self._get_input_to_process(last_human, context)

            options = {}
            if hasattr(context, "constraints") and isinstance(context.constraints, dict):
                options = context.constraints.get("writing_options") or {}

            if hasattr(self.writing_assistant, "process_request"):
                response = self.writing_assistant.process_request(
                    input_to_process, context, options=options
                )
                return self._handle_agent_response(response, context, "writing_assistant", input_to_process)
            else:
                return {"messages": [AIMessage(content="Writing assistant is not initialized.")], "context": context}

        except Exception as e:
            logger.error(f"Error in writing assistant: {e}")
            return {"messages": [AIMessage(content=f"Writing Assistant encountered an error: {str(e)}")]}

    def _reviewer_agent_node(self, state: AgentState):
        """Reviewer agent node"""
        try:
            messages = state["messages"]
            last_message = messages[-1].content if messages else ""
            context = state["context"]

            input_to_process = self._get_input_to_process(last_message, context)

            if hasattr(self.reviewer_agent, 'process_request'):
                response = self.reviewer_agent.process_request(input_to_process, context)
                return self._handle_agent_response(response, context, "reviewer_agent", input_to_process)
            else:
                # Fallback for legacy interface
                return {"messages": [AIMessage(content="Reviewer agent needs updating to new interface.")]}

        except Exception as e:
            logger.error(f"Error in reviewer agent: {e}")
            return {"messages": [AIMessage(content=f"Reviewer Agent encountered an error: {str(e)}")]}

    def _get_input_to_process(self, last_message: str, context: UserContext) -> str:
        """Get the input to process, using enriched input if available"""
        if hasattr(context, 'enriched_input') and context.enriched_input:
            logger.info("Using enriched input for agent")
            enriched = context.enriched_input
            context.enriched_input = None  # Clear after use
            return enriched
        return last_message

    def _handle_agent_response(self, response, context: UserContext, agent_name: str, original_input: str):
        """Handle agent response consistently across all agents"""
        # Handle agent needing more information
        if not response.success and response.instructions:
            context.pending_agent = agent_name
            context.pending_request = original_input

            if hasattr(response, 'updated_context') and response.updated_context:
                context = response.updated_context
                context.pending_agent = agent_name
                context.pending_request = original_input

            return {
                "messages": [AIMessage(content=response.user_message or "I need more information.")],
                "context": context
            }

        # Handle successful response
        if hasattr(context, 'pending_agent'):
            context.pending_agent = None
            context.pending_request = None

        if hasattr(response, 'updated_context') and response.updated_context:
            context = response.updated_context
            if hasattr(context, 'pending_agent'):
                context.pending_agent = None
                context.pending_request = None

        return {
            "messages": [AIMessage(content=response.user_message or f"{agent_name.title()} completed the task.")],
            "context": context
        }

    def _store_research_summaries(self, response, context: UserContext):
        """Store research summaries in context if available"""
        try:
            if response.success and hasattr(self.research_agent, 'collected_papers'):
                from src.models.models import ResearchSummary
                summaries = []
                for p in self.research_agent.collected_papers[:8]:
                    summaries.append(
                        ResearchSummary(
                            title=p.title,
                            authors=p.authors,
                            publication_year=p.year,
                            summary=(p.abstract[:500] + "...") if p.abstract and len(p.abstract) > 500 else (p.abstract or ""),
                            url=p.url,
                        )
                    )
                context.research_summaries = summaries
        except Exception as e:
            logger.warning(f"Could not store research summaries in context: {e}")
