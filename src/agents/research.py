from typing import List
from src.models.models import ResearchSummary, Paper, TopicEvaluation
from src.utils.logging import get_logger
from src.utils.academic_apis import search_papers
from src.utils.storage import save_papers, load_papers
from src.utils.openrouter_client import OpenRouterClient

logger = get_logger(__name__)

class ResearchAgent:
    def __init__(self):
        self.client = OpenRouterClient()
        self.collected_papers: List[Paper] = []
    
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
