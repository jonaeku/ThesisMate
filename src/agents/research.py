from typing import List
from src.models.models import (
    ResearchSummary, Paper, TopicEvaluation, UserContext, AgentResponse, 
    AgentInstruction, AgentCapabilityAssessment
)
from src.utils.custom_logging import get_logger
from src.utils.academic_apis import search_papers
from src.utils.storage import save_papers, load_papers
from src.utils.openrouter_client import OpenRouterClient


logger = get_logger(__name__)

class ResearchAgent:
    def __init__(self):
        self.client = OpenRouterClient()
        self.collected_papers: List[Paper] = []
        self.agent_name = "research_agent"
    
    def can_handle_request(self, user_input: str, context: UserContext) -> AgentCapabilityAssessment:
        """Dynamically assess if this agent can handle the request"""
        try:
            prompt = f"""You are a Research Agent that helps find and analyze academic papers and research.
            
Analyze this request and determine if you can handle it:

User request: "{user_input}"
Current context: Field: {context.field or 'Unknown'}, Interests: {context.interests or 'None'}

Can you handle this request? Consider:
- Is the user asking for papers, literature search, research analysis?
- Is the user asking to validate or research a specific topic?
- Do you have enough information to conduct a meaningful search?

Respond in JSON format:
{{
    "can_handle": true/false,
    "confidence": 0.0-1.0,
    "missing_info": ["list", "of", "missing", "information"],
    "reasoning": "explanation of your assessment",
    "suggested_questions": ["question1", "question2"]
}}"""

            messages = [
                {"role": "system", "content": "You are an intelligent research agent that assesses your own capabilities. Be honest about what you can and cannot do."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.3, max_tokens=400)
            
            if response:
                import json
                try:
                    assessment_data = json.loads(response.strip())
                    return AgentCapabilityAssessment(
                        can_handle=assessment_data.get("can_handle", False),
                        confidence=assessment_data.get("confidence", 0.0),
                        missing_info=assessment_data.get("missing_info", []),
                        reasoning=assessment_data.get("reasoning", "Assessment completed"),
                        suggested_questions=assessment_data.get("suggested_questions", [])
                    )
                except json.JSONDecodeError:
                    pass
            
            # Fallback assessment
            return self._fallback_assessment(user_input, context)
            
        except Exception as e:
            logger.error(f"Error in capability assessment: {e}")
            return AgentCapabilityAssessment(
                can_handle=False,
                confidence=0.0,
                reasoning=f"Error during assessment: {str(e)}"
            )
    
    def process_request(self, user_input: str, context: UserContext) -> AgentResponse:
        """Main method: Process user request dynamically"""
        logger.info(f"Research Agent processing: {user_input}")
        
        try:
            # First assess if we can handle this
            assessment = self.can_handle_request(user_input, context)
            
            if not assessment.can_handle:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    capability_assessment=assessment,
                    user_message="I don't think I'm the right agent for this request. Let me hand this back to the orchestrator."
                )
            
            # Check if we have enough specific information to conduct meaningful research
            if not self._has_enough_research_info(user_input, context):
                question = self._get_research_clarification_question(user_input, context)
                
                instruction = AgentInstruction(
                    requesting_agent=self.agent_name,
                    action_type="ask_user",
                    target="user",
                    message=question,
                    reasoning="Need specific topic information to conduct meaningful research"
                )
                
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    instructions=[instruction],
                    user_message=question
                )
            
            # If we can handle but need more info from capability assessment
            if assessment.confidence < 0.7 or assessment.missing_info:
                instructions = []
                if assessment.suggested_questions:
                    for question in assessment.suggested_questions:
                        instructions.append(AgentInstruction(
                            requesting_agent=self.agent_name,
                            action_type="ask_user",
                            target="user",
                            message=question,
                            reasoning=f"Need this information to conduct effective research: {assessment.reasoning}"
                        ))
                
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    instructions=instructions,
                    capability_assessment=assessment,
                    user_message="I need more specific information to help you effectively."
                )
            
            # Extract research query from user input
            research_query = self._extract_research_query(user_input, context)
            
            # Conduct research
            return self._conduct_research(research_query, user_input)
            
        except Exception as e:
            logger.error(f"Error in Research Agent: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                user_message=f"I encountered an error: {str(e)}"
            )
    
    def _has_enough_research_info(self, user_input: str, context: UserContext) -> bool:
        """Check if we have enough specific information to conduct meaningful research"""
        try:
            # Use LLM to determine if the input contains a specific research topic
            prompt = f"""You are a strict research assistant. Analyze if this request contains enough SPECIFIC information to conduct meaningful academic research.

User request: "{user_input}"
Context: Field: {context.field or 'Unknown'}, Interests: {context.interests or 'None'}

STRICT CRITERIA - A request has ENOUGH information ONLY if it contains:
- A SPECIFIC research topic, technology, concept, or domain (e.g., "machine learning", "neural networks", "blockchain", "climate change")
- Clear subject matter that can be directly searched in academic databases
- NOT just generic words like "papers", "research", "help", "find"

A request has NOT ENOUGH information if it's:
- Vague requests for help ("help me", "find papers", "research help", "I need help")
- Generic requests without specific topics ("find me papers", "do research")
- Just asking for assistance without naming a topic
- Contains only generic research words without specific subject matter

EXAMPLES:
✅ ENOUGH: "Find papers on machine learning in healthcare"
✅ ENOUGH: "I need research on neural networks" 
✅ ENOUGH: "Research blockchain technology"
✅ ENOUGH: "Papers about climate change"
❌ NOT ENOUGH: "Help me find papers"
❌ NOT ENOUGH: "I need research help"
❌ NOT ENOUGH: "Find me some papers"
❌ NOT ENOUGH: "Can you help with research"
❌ NOT ENOUGH: "I want to do research"

Be VERY STRICT. Answer with ONLY "ENOUGH" or "NOT ENOUGH"."""

            messages = [
                {"role": "system", "content": "You are a strict gatekeeper. Only allow requests with specific research topics. Be very strict about requiring concrete subject matter."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.0, max_tokens=20)
            
            if response and "ENOUGH" in response.upper() and "NOT ENOUGH" not in response.upper():
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error checking research info sufficiency: {e}")
            # If error, be conservative and ask for more info
            return False
    
    def _get_research_clarification_question(self, user_input: str, context: UserContext) -> str:
        """Generate an appropriate clarification question for research"""
        try:
            prompt = f"""The user made a vague research request. Generate a helpful clarification question.

User request: "{user_input}"
Context: Field: {context.field or 'Unknown'}, Interests: {context.interests or 'None'}

Generate a specific question that will help me understand what they want to research. The question should:
- Ask for a specific research topic or subject
- Be helpful and encouraging
- Guide them toward providing actionable information

Examples:
- "What specific topic would you like me to research? (e.g., machine learning, neural networks, AI ethics)"
- "Could you tell me what subject or technology you'd like me to find papers about?"
- "What research area are you interested in exploring?"

Generate just the question, nothing else."""

            messages = [
                {"role": "system", "content": "Generate helpful clarification questions for research requests."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.3, max_tokens=100)
            
            if response and response.strip():
                return response.strip()
            
            # Fallback question
            return "What specific topic would you like me to research? Please provide a clear subject or research area (e.g., 'machine learning in healthcare', 'neural networks', 'AI ethics')."
            
        except Exception as e:
            logger.error(f"Error generating clarification question: {e}")
            return "What specific topic would you like me to research? Please provide a clear subject or research area."
    
    def _extract_research_query(self, user_input: str, context: UserContext) -> str:
        """Extract the actual research query from user input"""
        try:
            prompt = f"""Extract the main research topic/query from this request:

User request: "{user_input}"
Context: Field: {context.field or 'Unknown'}, Interests: {context.interests or 'None'}

What should I search for in academic databases? Provide a concise search query (2-5 words) that would find relevant papers.

Examples:
- "I need papers on machine learning in healthcare" → "machine learning healthcare"
- "Find research about neural networks for image processing" → "neural networks image processing"
- "I want to research AI ethics" → "AI ethics"

Search query:"""

            messages = [
                {"role": "system", "content": "Extract concise search queries from user requests."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.2, max_tokens=50)
            
            if response and response.strip():
                return response.strip().replace('"', '')
            
            # Fallback: use user input directly
            return user_input
            
        except Exception as e:
            logger.error(f"Error extracting research query: {e}")
            return user_input
    
    def _conduct_research(self, query: str, original_request: str) -> AgentResponse:
        """Conduct research and format results"""
        try:
            # Search for papers
            papers = self.collect_papers(query, max_results=20)
            
            if not papers:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    user_message=f"I couldn't find any papers for '{query}'. Could you try a different search term or be more specific?"
                )
            
            # Format results for user
            formatted_message = self._format_research_results(papers, query)
            
            return AgentResponse(
                success=True,
                agent_name=self.agent_name,
                result=papers,
                user_message=formatted_message
            )
            
        except Exception as e:
            logger.error(f"Error conducting research: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                user_message=f"I encountered an error while searching for papers: {str(e)}"
            )
    
    def _format_research_results(self, papers: List[Paper], query: str) -> str:
        """Format research results for user presentation"""
        if not papers:
            return f"I couldn't find any papers for '{query}'."
        
        message = f"I found {len(papers)} relevant papers for '{query}':\n\n"
        
        # Show top 5 papers with details
        for i, paper in enumerate(papers[:5], 1):
            message += f"**{i}. {paper.title}** ({paper.year})\n"
            message += f"👥 Authors: {', '.join(paper.authors[:3])}\n"
            
            # Show abstract snippet
            abstract_snippet = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
            message += f"📄 Abstract: {abstract_snippet}\n"
            
            if paper.relevance_score > 0:
                message += f"📊 Relevance: {paper.relevance_score:.2f}/1.0\n"
            
            if paper.url:
                message += f"🔗 Link: {paper.url}\n"
            
            message += "\n"
        
        if len(papers) > 5:
            message += f"... and {len(papers) - 5} more papers found.\n\n"
        
        # Don't ask follow-up questions - just present the results
        message += "Research completed! These papers should help with your research."
        return message
    
    def _fallback_assessment(self, user_input: str, context: UserContext) -> AgentCapabilityAssessment:
        """Simple fallback assessment when LLM fails"""
        user_lower = user_input.lower()
        research_keywords = ['paper', 'research', 'literature', 'study', 'article', 'publication', 'find', 'search']
        
        has_research_keywords = any(keyword in user_lower for keyword in research_keywords)
        
        if has_research_keywords:
            return AgentCapabilityAssessment(
                can_handle=True,
                confidence=0.7,
                reasoning="Request appears to be about research or finding papers"
            )
        
        return AgentCapabilityAssessment(
            can_handle=False,
            confidence=0.2,
            reasoning="Request doesn't appear to be about research or papers"
        )
    
    def respond(self, topic: str) -> list[ResearchSummary]:
        """Legacy method for compatibility - converts Papers to ResearchSummary"""
        papers = self.collect_papers(topic, max_results=10)
        
        # Convert Paper objects to ResearchSummary for backward compatibility
        summaries = []
        for paper in papers:
            summary = ResearchSummary(
                title=paper.title,
                authors=paper.authors,
                publication_year=paper.year,
                summary=paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract,
                url=paper.url
            )
            summaries.append(summary)
        
        return summaries
    
    def collect_papers(self, topic: str, max_results: int = 40) -> List[Paper]:
        """Collect papers on a given topic and use LLM to score relevance"""
        logger.info(f"Collecting papers for topic: {topic}")
        
        try:
            # Search for papers using our academic APIs
            papers = search_papers(topic, max_results=max_results)
            
            if not papers:
                return []
            
            # Use LLM to score relevance and filter papers
            scored_papers = self._llm_score_relevance(papers, topic)
            
            # Store collected papers
            self.collected_papers = scored_papers
            
            # Save to storage
            save_papers(scored_papers, f"data/papers_{topic.replace(' ', '_')}.json")
            
            logger.info(f"Collected {len(scored_papers)} papers for topic: {topic}")
            return scored_papers
            
        except Exception as e:
            logger.error(f"Error collecting papers for topic {topic}: {e}")
            return []
    
    def evaluate_topic(self, topic: str) -> TopicEvaluation:
        """Use LLM to evaluate the feasibility of a research topic"""
        logger.info(f"Evaluating topic: {topic}")
        
        try:
            # Quick search to get sample papers
            papers = search_papers(topic, max_results=20)
            
            if not papers:
                return TopicEvaluation(
                    topic=topic,
                    paper_count=0,
                    feasibility_score=0.0,
                    sample_papers=[],
                    research_gaps=["No papers found - topic may be too narrow or novel"],
                    confidence_score=0.1
                )
            
            # Use LLM to analyze the topic feasibility
            evaluation = self._llm_evaluate_topic(topic, papers)
            
            logger.info(f"Topic evaluation complete: {topic} - Score: {evaluation.feasibility_score:.2f}")
            return evaluation
            
        except Exception as e:
            logger.error(f"Error evaluating topic {topic}: {e}")
            return TopicEvaluation(
                topic=topic,
                paper_count=0,
                feasibility_score=0.0,
                sample_papers=[],
                research_gaps=[f"Error during evaluation: {str(e)}"],
                confidence_score=0.0
            )
    
    def deep_research(self, topic: str, max_results: int = 60) -> dict:
        """Use LLM to perform comprehensive research analysis"""
        logger.info(f"Starting deep research for topic: {topic}")
        
        try:
            # Collect comprehensive set of papers
            papers = self.collect_papers(topic, max_results=max_results)
            
            if not papers:
                return {
                    "topic": topic,
                    "total_papers": 0,
                    "error": "No papers found for this topic"
                }
            
            # Use LLM to analyze the research landscape
            analysis = self._llm_analyze_research_landscape(topic, papers)
            
            logger.info(f"Deep research complete for topic: {topic}")
            return analysis
            
        except Exception as e:
            logger.error(f"Error in deep research for topic {topic}: {e}")
            return {
                "topic": topic,
                "total_papers": 0,
                "error": f"Error during deep research: {str(e)}"
            }
    
    def _llm_score_relevance(self, papers: List[Paper], topic: str) -> List[Paper]:
        """Use LLM to score paper relevance to the topic"""
        try:
            # Prepare paper summaries for LLM
            paper_summaries = []
            for i, paper in enumerate(papers):
                summary = f"{i+1}. Title: {paper.title}\n   Authors: {', '.join(paper.authors[:3])}\n   Year: {paper.year}\n   Abstract: {paper.abstract[:300]}..."
                paper_summaries.append(summary)
            
            papers_text = "\n\n".join(paper_summaries)
            
            prompt = f"""You are a research expert. Analyze these papers for relevance to the topic: "{topic}"

Papers:
{papers_text}

For each paper, provide a relevance score from 0.0 to 1.0 based on how well it matches the topic.
Consider:
- Title relevance to the topic
- Abstract content alignment
- Methodological relevance
- Recency (newer papers get slight boost)

Respond with ONLY a JSON array of scores in the same order as the papers:
[0.8, 0.6, 0.9, 0.3, ...]"""

            messages = [
                {"role": "system", "content": "You are a research analysis expert. Provide precise relevance scores."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.3, max_tokens=2000)
            
            if response:
                # Parse the scores
                import json
                try:
                    scores = json.loads(response.strip())
                    for i, score in enumerate(scores):
                        if i < len(papers):
                            papers[i].relevance_score = float(score)
                except:
                    # Fallback: simple keyword matching
                    topic_words = set(topic.lower().split())
                    for paper in papers:
                        title_words = set(paper.title.lower().split())
                        matches = len(topic_words.intersection(title_words))
                        paper.relevance_score = min(1.0, matches / len(topic_words))
            
            # Sort by relevance score
            papers.sort(key=lambda p: p.relevance_score, reverse=True)
            return papers
            
        except Exception as e:
            logger.error(f"Error in LLM relevance scoring: {e}")
            # Fallback to simple scoring
            topic_words = set(topic.lower().split())
            for paper in papers:
                title_words = set(paper.title.lower().split())
                matches = len(topic_words.intersection(title_words))
                paper.relevance_score = min(1.0, matches / len(topic_words))
            
            papers.sort(key=lambda p: p.relevance_score, reverse=True)
            return papers
    
    def _llm_evaluate_topic(self, topic: str, papers: List[Paper]) -> TopicEvaluation:
        """Use LLM to evaluate topic feasibility"""
        try:
            # Prepare paper data for analysis
            paper_data = []
            for paper in papers[:10]:  # Top 10 papers
                paper_data.append({
                    "title": paper.title,
                    "year": paper.year,
                    "authors": paper.authors[:3],
                    "abstract_snippet": paper.abstract[:200]
                })
            
            prompt = f"""You are a research advisor. Evaluate the feasibility of this research topic: "{topic}"

Based on these {len(papers)} papers found:
{paper_data}

Provide your analysis in this JSON format:
{{
    "feasibility_score": 0.0-1.0,
    "confidence_score": 0.0-1.0,
    "research_gaps": ["gap1", "gap2", "gap3"],
    "reasoning": "Brief explanation of your assessment"
}}

Consider:
- Number of existing papers (more = easier to build on, but less novel)
- Recency of research (recent = active field)
- Diversity of approaches
- Potential for novel contributions"""

            messages = [
                {"role": "system", "content": "You are an expert research advisor who evaluates research topic feasibility."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.4, max_tokens=800)
            
            if response:
                import json
                try:
                    analysis = json.loads(response.strip())
                    
                    # Score papers for relevance using simple method
                    scored_papers = []
                    topic_words = set(topic.lower().split())
                    for paper in papers[:5]:
                        title_words = set(paper.title.lower().split())
                        matches = len(topic_words.intersection(title_words))
                        paper.relevance_score = min(1.0, matches / len(topic_words))
                        scored_papers.append(paper)
                    
                    return TopicEvaluation(
                        topic=topic,
                        paper_count=len(papers),
                        feasibility_score=analysis.get("feasibility_score", 0.5),
                        sample_papers=scored_papers,
                        research_gaps=analysis.get("research_gaps", []),
                        confidence_score=analysis.get("confidence_score", 0.5)
                    )
                except:
                    pass
            
            # Fallback evaluation
            return TopicEvaluation(
                topic=topic,
                paper_count=len(papers),
                feasibility_score=min(1.0, len(papers) / 30.0),
                sample_papers=papers[:5],
                research_gaps=["LLM analysis unavailable - manual review recommended"],
                confidence_score=0.6
            )
            
        except Exception as e:
            logger.error(f"Error in LLM topic evaluation: {e}")
            return TopicEvaluation(
                topic=topic,
                paper_count=len(papers),
                feasibility_score=0.5,
                sample_papers=papers[:5],
                research_gaps=[f"Evaluation error: {str(e)}"],
                confidence_score=0.3
            )
    
    def _llm_analyze_research_landscape(self, topic: str, papers: List[Paper]) -> dict:
        """Use LLM to analyze the research landscape"""
        try:
            # Prepare comprehensive paper data
            paper_summaries = []
            for paper in papers[:20]:  # Top 20 papers
                summary = f"- {paper.title} ({paper.year}) by {', '.join(paper.authors[:2])}"
                paper_summaries.append(summary)
            
            papers_text = "\n".join(paper_summaries)
            
            prompt = f"""You are a research analyst. Analyze the research landscape for: "{topic}"

Based on these {len(papers)} papers:
{papers_text}

Provide a comprehensive analysis in JSON format:
{{
    "research_trends": ["trend1", "trend2", "trend3"],
    "key_methodologies": ["method1", "method2"],
    "leading_researchers": ["researcher1", "researcher2"],
    "research_gaps": ["gap1", "gap2", "gap3"],
    "future_directions": ["direction1", "direction2"],
    "summary": "Brief overview of the field"
}}

Focus on identifying patterns, gaps, and opportunities in the research."""

            messages = [
                {"role": "system", "content": "You are an expert research analyst who identifies trends and opportunities."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.5, max_tokens=1200)
            
            if response:
                import json
                try:
                    analysis = json.loads(response.strip())
                    
                    return {
                        "topic": topic,
                        "total_papers": len(papers),
                        "top_papers": papers[:10],
                        "research_trends": analysis.get("research_trends", []),
                        "key_methodologies": analysis.get("key_methodologies", []),
                        "leading_researchers": analysis.get("leading_researchers", []),
                        "research_gaps": analysis.get("research_gaps", []),
                        "future_directions": analysis.get("future_directions", []),
                        "summary": analysis.get("summary", "Analysis completed"),
                        "llm_analysis": True
                    }
                except:
                    pass
            
            # Fallback analysis
            return {
                "topic": topic,
                "total_papers": len(papers),
                "top_papers": papers[:10],
                "research_trends": ["LLM analysis unavailable"],
                "research_gaps": ["Manual analysis recommended"],
                "summary": f"Found {len(papers)} papers on {topic}",
                "llm_analysis": False
            }
            
        except Exception as e:
            logger.error(f"Error in LLM landscape analysis: {e}")
            return {
                "topic": topic,
                "total_papers": len(papers),
                "error": f"Analysis error: {str(e)}",
                "llm_analysis": False
            }