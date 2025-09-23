from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, MessageGraph

from src.agents.research import ResearchAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.structure import StructureAgent
from src.agents.topic_scout import TopicScoutAgent
from src.agents.writing import WritingAssistantAgent

from src.utils.config import get_env
from src.utils.logging import get_logger
from src.utils.openrouter_client import OpenRouterClient

logger = get_logger(__name__)

class Orchestrator:
    def __init__(self):
        self.api_key = get_env("OPENROUTER_API_KEY")
        logger.info(f"API Key: {self.api_key}")
        self.client = OpenRouterClient()
        
        # Keep agents for future enhancement
        self.topic_scout = TopicScoutAgent()
        self.research_agent = ResearchAgent()
        self.structure_agent = StructureAgent()
        self.writing_assistant = WritingAssistantAgent()
        self.reviewer_agent = ReviewerAgent()

        self.graph = MessageGraph()
        self.graph.add_node("topic_scout", self.topic_scout.respond)
        self.graph.add_node("research_agent", self.research_agent.respond)
        self.graph.add_node("structure_agent", self.structure_agent.respond)
        self.graph.add_node("writing_assistant", self.writing_assistant.respond)
        self.graph.add_node("reviewer_agent", self.reviewer_agent.respond)

        self.graph.add_edge("topic_scout", "research_agent")
        self.graph.add_edge("research_agent", "structure_agent")
        self.graph.add_edge("structure_agent", "writing_assistant")
        self.graph.add_edge("writing_assistant", "reviewer_agent")
        self.graph.add_edge("reviewer_agent", END)

        self.graph.set_entry_point("topic_scout")
        self.runnable = self.graph.compile()

    def run(self, query: str) -> str:
        """
        Route queries to appropriate agents or use direct LLM response.
        """
        query_lower = query.lower()
        
        # Simple routing: if query contains research keywords, use Research Agent
        research_keywords = ['research', 'papers', 'literature', 'topic evaluation', 'feasibility', 'deep research']
        if any(keyword in query_lower for keyword in research_keywords):
            logger.info("Routing to Research Agent")
            try:
                # Extract topic (simple approach)
                topic = query.replace('research', '').replace('papers', '').replace('literature', '').strip()
                if not topic:
                    topic = query
                
                # Use Research Agent
                papers = self.research_agent.collect_papers(topic, max_results=10)
                
                # Simple formatting
                if papers:
                    result = f"Found {len(papers)} papers on '{topic}':\n\n"
                    for i, paper in enumerate(papers[:5], 1):
                        result += f"{i}. **{paper.title}** ({paper.year})\n"
                        result += f"   Authors: {', '.join(paper.authors[:3])}\n"
                        result += f"   Relevance: {paper.relevance_score:.2f}\n"
                        if paper.url:
                            result += f"   Link: {paper.url}\n"
                        result += "\n"
                    return result
                else:
                    return f"No papers found for topic: {topic}"
                    
            except Exception as e:
                logger.error(f"Research Agent error: {e}")
                return f"Error during research: {str(e)}"
        
        # Default: use direct LLM response
        messages = [
            {
                "role": "system",
                "content": "You are ThesisMate, an AI assistant that helps with academic thesis writing and research. Provide helpful, accurate, and detailed responses."
            },
            {
                "role": "user",
                "content": query
            }
        ]
        
        response = self.client.chat_completion(messages, temperature=0.7, max_tokens=1500)
        
        if response:
            logger.info("Successfully got response from OpenRouter")
            return response
        else:
            logger.error("Failed to get response from OpenRouter")
            return "I apologize, but I'm having trouble processing your request right now. Please try again later."
