from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import END, StateGraph
from typing import TypedDict, Annotated, Literal
import operator

from src.agents.research import ResearchAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.structure import StructureAgent
from src.agents.topic_scout import TopicScoutAgent
from src.agents.writing import WritingAssistantAgent
from src.models.models import UserContext

from src.utils.config import get_env
from src.utils.logging import get_logger
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
        """Supervisor decides which agent to call next"""
        try:
            messages = state["messages"]
            last_message = messages[-1].content if messages else ""
            context = state["context"]
            
            # Check if we just came from an agent that set a pending_agent
            # If so, we should END immediately to return the question to the user
            if hasattr(context, 'pending_agent') and context.pending_agent and len(messages) > 1:
                # The last message is from an agent asking a question
                # We should END here to return the question to the user
                logger.info(f"Agent asked question, ending conversation to wait for user response")
                return {"next_agent": "END"}
            
            # Check if the last message looks like completed results from an agent
            # If so, END the conversation instead of routing to another agent
            if len(messages) > 1 and self._is_completed_result(last_message):
                logger.info(f"Agent completed task, ending conversation")
                return {"next_agent": "END"}
            
            # Use LLM to decide which agent should handle this
            agent_choice = self._choose_agent_with_llm(last_message, context)
            
            logger.info(f"Supervisor routing to: {agent_choice}")
            
            # Update state with next agent decision
            return {"next_agent": agent_choice}
                
        except Exception as e:
            logger.error(f"Error in supervisor: {e}")
            return {
                "next_agent": "END",
                "messages": [AIMessage(content=f"I encountered an error: {str(e)}")]
            }
    
    def _is_completed_result(self, message: str) -> bool:
        """Check if a message looks like completed results from an agent"""
        # Look for patterns that indicate completed work
        completion_indicators = [
            "Research completed!",
            "I found",
            "papers found",
            "Topic Scout processed",
            "Here are the results",
            "Analysis complete",
            "**1.", "**2.", "**3.",  # Formatted lists
            "👥 Authors:",  # Research results format
            "📄 Abstract:",  # Research results format
        ]
        
        return any(indicator in message for indicator in completion_indicators)

    def _supervisor_decision(self, state: AgentState) -> str:
        """Return the next agent to call"""
        return state["next_agent"]

    def _choose_agent_with_llm(self, user_input: str, context: UserContext) -> str:
        """Use LLM to choose the appropriate agent"""
        try:
            # Check if there's a pending agent waiting for user response
            if hasattr(context, 'pending_agent') and context.pending_agent:
                logger.info(f"Routing back to pending agent: {context.pending_agent}")
                pending_agent = context.pending_agent
                
                # IMPORTANT: Enrich the user input with context for the pending agent
                if hasattr(context, 'pending_request') and context.pending_request:
                    # Combine the original request with the user's response
                    enriched_input = f"Original request: {context.pending_request}\nUser's additional info: {user_input}"
                    logger.info(f"Enriching input for pending agent: {enriched_input[:100]}...")
                    # Store the enriched input in the context so the agent gets it
                    context.enriched_input = enriched_input
                
                # Clear the pending agent to avoid loops
                context.pending_agent = None
                context.pending_request = None
                return pending_agent

            # Choose agent for new request
            prompt = f"""Choose the best agent for this request:

User request: "{user_input}"
Context: Field: {context.field or 'Unknown'}, Interests: {context.interests or 'None'}

Available agents:
- topic_scout: Finds thesis topics, research areas, handles field/interest info
- research_agent: Searches papers, literature analysis  
- structure_agent: Creates outlines, thesis structure
- writing_assistant: Helps with writing content
- reviewer_agent: Reviews and gives feedback

ROUTING RULES:
- Topic suggestions, research areas, field/interest info → topic_scout
- Paper search, literature analysis → research_agent  
- Thesis structure, outlines → structure_agent
- Writing content, drafting → writing_assistant
- Review, feedback → reviewer_agent

Respond with just the agent name (e.g., "topic_scout")."""

            messages = [
                {"role": "system", "content": "You are a supervisor that routes requests to agents. Respond with only the agent name."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.1, max_tokens=20)
            
            if response:
                agent_name = response.strip().lower()
                valid_agents = ["topic_scout", "research_agent", "structure_agent", "writing_assistant", "reviewer_agent"]
                if agent_name in valid_agents:
                    return agent_name
            
            # Fallback to keyword matching
            return self._keyword_route(user_input)
            
        except Exception as e:
            logger.error(f"LLM routing failed: {e}")
            return self._keyword_route(user_input)

    def _keyword_route(self, query: str) -> str:
        """Simple keyword-based routing as fallback"""
        query_lower = query.lower()
        
        if any(word in query_lower for word in ['topic', 'suggestion', 'field', 'interest', 'brainstorm']):
            return "topic_scout"
        elif any(word in query_lower for word in ['paper', 'research', 'literature', 'study', 'article']):
            return "research_agent"
        elif any(word in query_lower for word in ['outline', 'structure', 'organize', 'chapter']):
            return "structure_agent"
        elif any(word in query_lower for word in ['write', 'draft', 'content', 'writing']):
            return "writing_assistant"
        elif any(word in query_lower for word in ['review', 'feedback', 'improve', 'check']):
            return "reviewer_agent"
        
        return "topic_scout"  # Default

    # Agent nodes - each processes with their respective agent
    def _topic_scout_node(self, state: AgentState):
        """Topic Scout agent node"""
        try:
            messages = state["messages"]
            last_message = messages[-1].content if messages else ""
            context = state["context"]
            
            # Use enriched input if available (for follow-up responses)
            input_to_process = last_message
            if hasattr(context, 'enriched_input') and context.enriched_input:
                input_to_process = context.enriched_input
                logger.info(f"Using enriched input for topic scout")
                # Clear the enriched input after using it
                context.enriched_input = None
            
            if hasattr(self.topic_scout, 'process_request'):
                response = self.topic_scout.process_request(input_to_process, context)
                
                # Handle agent instructions (like asking follow-up questions)
                if not response.success and response.instructions:
                    # Agent needs more information - store the pending agent and ask user
                    context.pending_agent = "topic_scout"
                    context.pending_request = input_to_process
                    
                    # Update context if provided
                    if hasattr(response, 'updated_context') and response.updated_context:
                        context = response.updated_context
                        context.pending_agent = "topic_scout"
                        context.pending_request = input_to_process
                    
                    # Return the question to the user and END the conversation
                    return {
                        "messages": [AIMessage(content=response.user_message or "I need more information.")],
                        "context": context
                    }
                
                # Normal successful response - clear any pending agent
                if hasattr(context, 'pending_agent'):
                    context.pending_agent = None
                    context.pending_request = None
                
                # Update context if provided
                if hasattr(response, 'updated_context') and response.updated_context:
                    context = response.updated_context
                    # Make sure to clear pending agent from updated context too
                    if hasattr(context, 'pending_agent'):
                        context.pending_agent = None
                        context.pending_request = None
                
                return {
                    "messages": [AIMessage(content=response.user_message or "Topic Scout processed your request.")],
                    "context": context
                }
            else:
                # Fallback to legacy interface
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
            
            # Use enriched input if available (for follow-up responses)
            input_to_process = last_message
            if hasattr(context, 'enriched_input') and context.enriched_input:
                input_to_process = context.enriched_input
                logger.info(f"Using enriched input for research agent")
                # Clear the enriched input after using it
                context.enriched_input = None
            
            if hasattr(self.research_agent, 'process_request'):
                response = self.research_agent.process_request(input_to_process, context)
                
                # Handle agent instructions (like asking follow-up questions)
                if not response.success and response.instructions:
                    # Agent needs more information - store the pending agent and ask user
                    context.pending_agent = "research_agent"
                    context.pending_request = input_to_process
                    
                    # Return the question to the user and END the conversation
                    return {
                        "messages": [AIMessage(content=response.user_message or "I need more information.")],
                        "context": context
                    }
                
                # Normal successful response - clear any pending agent
                if hasattr(context, 'pending_agent'):
                    context.pending_agent = None
                    context.pending_request = None
                
                return {
                    "messages": [AIMessage(content=response.user_message or "Research completed.")],
                    "context": context
                }
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
            
            response_text = self.structure_agent.respond(last_message, [])
            return {"messages": [AIMessage(content=str(response_text))]}
                
        except Exception as e:
            logger.error(f"Error in structure agent: {e}")
            return {"messages": [AIMessage(content=f"Structure Agent encountered an error: {str(e)}")]}

    def _writing_assistant_node(self, state: AgentState):
        """Writing assistant node"""
        try:
            messages = state["messages"]
            last_message = messages[-1].content if messages else ""
            
            response_text = self.writing_assistant.respond({"title": last_message}, [])
            return {"messages": [AIMessage(content=response_text)]}
                
        except Exception as e:
            logger.error(f"Error in writing assistant: {e}")
            return {"messages": [AIMessage(content=f"Writing Assistant encountered an error: {str(e)}")]}

    def _reviewer_agent_node(self, state: AgentState):
        """Reviewer agent node"""
        try:
            messages = state["messages"]
            last_message = messages[-1].content if messages else ""
            
            response_text = self.reviewer_agent.respond(last_message)
            return {"messages": [AIMessage(content=response_text)]}
                
        except Exception as e:
            logger.error(f"Error in reviewer agent: {e}")
            return {"messages": [AIMessage(content=f"Reviewer Agent encountered an error: {str(e)}")]}
