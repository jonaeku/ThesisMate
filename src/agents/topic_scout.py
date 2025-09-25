from typing import List, Optional
from src.models.models import (
    TopicSuggestion, TopicScoutResponse, UserContext, AgentResponse, 
    AgentInstruction, AgentCapabilityAssessment, TopicEvaluation
)
from src.utils.logging import get_logger
from src.utils.openrouter_client import OpenRouterClient

logger = get_logger(__name__)

class TopicScoutAgent:
    def __init__(self, research_tool=None):
        """Initialize Topic Scout Agent with Research Agent as tool"""
        self.research_tool = research_tool
        self.client = OpenRouterClient()
        self.agent_name = "topic_scout"
    
    def can_handle_request(self, user_input: str, context: UserContext) -> AgentCapabilityAssessment:
        """Let the LLM decide if this is a topic-related request"""
        try:
            prompt = f"""You are a Topic Scout Agent that helps find thesis topics and research topics.

Analyze this request and determine if you can handle it:

User request: "{user_input}"
Current context: Field: {context.field or 'Not set'}, Interests: {context.interests or 'Not set'}

You CAN handle requests about:
- Finding thesis topics
- Suggesting research topics  
- Topic exploration and brainstorming
- Research area recommendations
- Academic topic guidance
- Providing field of study information (like "Computer Science", "Biology")
- Providing interest areas (like "AI", "Machine Learning", "Healthcare")

You CANNOT handle requests about:
- Writing content (conclusions, introductions, etc.)
- Research methodology
- Literature reviews
- Data analysis
- Citation formatting

IMPORTANT: If the user is providing information that could be their field of study or interests (even if it seems brief), you should handle it as part of the topic research process. But if its only e.g. Medicine ask for more details.

Answer with just "YES" or "NO" and a brief reason why."""

            messages = [
                {"role": "system", "content": "You are a helpful topic scout agent. Be generous in accepting topic-related requests and information."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.1, max_tokens=100)
            
            if response and "YES" in response.upper():
                return AgentCapabilityAssessment(
                    can_handle=True,
                    confidence=0.9,
                    missing_info=[],
                    reasoning="This is a topic-related request I can handle",
                    suggested_questions=[]
                )
            elif response and "NO" in response.upper():
                return AgentCapabilityAssessment(
                    can_handle=False,
                    confidence=0.9,
                    missing_info=[],
                    reasoning=response.strip(),
                    suggested_questions=[]
                )
            else:
                # If unclear, be more generous for topic-related things
                return AgentCapabilityAssessment(
                    can_handle=True,
                    confidence=0.7,
                    missing_info=[],
                    reasoning="Assuming this is topic-related",
                    suggested_questions=[]
                )
                
        except Exception as e:
            logger.error(f"Error in capability assessment: {e}")
            # If error, still try to be helpful
            return AgentCapabilityAssessment(
                can_handle=True,
                confidence=0.6,
                missing_info=[],
                reasoning=f"Error in assessment but trying to help: {str(e)}",
                suggested_questions=[]
            )
    
    def process_request(self, user_input: str, context: UserContext) -> AgentResponse:
        """Main processing method - smart about context and follow-ups"""
        logger.info(f"Topic Scout processing: {user_input}")
        
        try:
            # Step 1: Try to understand if this is providing missing context
            updated_context = self._update_context_from_input(user_input, context)
            
            # Step 2: Check if I can handle this request (with updated context)
            assessment = self.can_handle_request(user_input, updated_context)
            
            if not assessment.can_handle:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    capability_assessment=assessment,
                    user_message=f"I don't think I can help with this request. {assessment.reasoning}"
                )
            
            # Step 3: Do I have enough information to generate topics?
            if not self._has_enough_info(updated_context):
                # Ask the orchestrator to get more info
                question = self._get_next_question(updated_context)
                
                instruction = AgentInstruction(
                    requesting_agent=self.agent_name,
                    action_type="ask_user",
                    target="user",
                    message=question,
                    reasoning="Need this information to generate relevant topics"
                )
                
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    instructions=[instruction],
                    user_message=question,
                    updated_context=updated_context  # Pass updated context back
                )
            
            # Step 4: I have enough info - generate topics
            topics = self._generate_topics(user_input, updated_context)
            
            if not topics:
                return AgentResponse(
                    success=False,
                    agent_name=self.agent_name,
                    user_message="I couldn't generate suitable topics. Could you provide more specific information about your interests?",
                    updated_context=updated_context
                )
            
            # Step 5: Validate topics with research agent if available
            if self.research_tool:
                topics = self._validate_topics_with_research(topics)
            
            # Step 6: Format and return results
            formatted_message = self._format_topics_for_user(topics)
            
            return AgentResponse(
                success=True,
                agent_name=self.agent_name,
                result=topics,
                user_message=formatted_message,
                updated_context=updated_context
            )
            
        except Exception as e:
            logger.error(f"Error in Topic Scout: {e}")
            return AgentResponse(
                success=False,
                agent_name=self.agent_name,
                user_message=f"I encountered an error: {str(e)}"
            )
    
    def _update_context_from_input(self, user_input: str, context: UserContext) -> UserContext:
        """Smart context update - understand when user is providing field/interests"""
        try:
            prompt = f"""Analyze if the user is providing field of study or interests information.

User input: "{user_input}"
Current context:
- Field: {context.field or 'Not set'}
- Interests: {context.interests or 'Not set'}

IMPORTANT: Distinguish between requests for help and actual field/interest information:

REQUESTS FOR HELP (DO NOT extract as field/interests):
- "Please help me with topic research"
- "I need help finding topics"
- "Can you help me with research"
- "I want topic suggestions"
- "Help me find thesis topics"

FIELD EXTRACTION RULES:
- Only extract as field if it's a broad academic discipline
- Examples: "Computer Science", "Biology", "Medicine", "Psychology", "Engineering"
- If field is already set, don't overwrite it unless explicitly stated (e.g., "My field is X")

INTEREST EXTRACTION RULES:
- Extract as interests if it's a specific topic, specialization, or research area
- Examples: "AI", "Machine Learning", "Neurology", "Rhinoplasty", "Neural Networks"
- If user provides specific medical specialties like "Neurology", "Cardiology" → interests
- If user provides specific procedures like "Rhinoplastic", "Surgery" → interests
- Always ADD to existing interests, don't replace them

Context-aware decisions:
- If field is already "Medicine" and user says "Neurology" → add to interests
- If field is already "Computer Science" and user says "AI" → add to interests
- If no field set and user says broad term like "Medicine" → field
- If no field set and user says specific term like "Neurology" → could be field OR interest

Respond in JSON format:
{{
    "field": "extracted field or null",
    "interests": ["list", "of", "interests"] or null
}}

Examples:
- "Computer Science" → {{"field": "Computer Science", "interests": null}}
- "AI and Machine Learning" → {{"field": null, "interests": ["AI", "Machine Learning"]}}
- "Neurology" (when field=Medicine) → {{"field": null, "interests": ["Neurology"]}}
- "Rhinoplastic" → {{"field": null, "interests": ["Rhinoplastic"]}}
- "Please help me with topic research" → {{"field": null, "interests": null}}"""

            messages = [
                {"role": "system", "content": "You are a context extractor. Extract field and interests from user input. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.1, max_tokens=200)
            
            if response:
                try:
                    import json
                    # Clean the response to handle markdown code blocks
                    response_clean = response.strip()
                    if '```json' in response_clean:
                        start = response_clean.find('```json') + 7
                        end = response_clean.find('```', start)
                        if end != -1:
                            response_clean = response_clean[start:end].strip()
                    elif '```' in response_clean:
                        start = response_clean.find('```') + 3
                        end = response_clean.find('```', start)
                        if end != -1:
                            response_clean = response_clean[start:end].strip()
                    
                    extracted = json.loads(response_clean)
                    
                    # Create updated context with proper interest merging
                    new_field = extracted.get("field") or context.field
                    extracted_interests = extracted.get("interests")
                    
                    # Handle interest merging properly
                    if extracted_interests:
                        if context.interests:
                            # Merge with existing interests, avoiding duplicates
                            existing_interests = context.interests if isinstance(context.interests, list) else []
                            new_interests = existing_interests + [interest for interest in extracted_interests if interest not in existing_interests]
                        else:
                            new_interests = extracted_interests
                    else:
                        new_interests = context.interests
                    
                    # If we extracted something new, create updated context
                    if new_field != context.field or new_interests != context.interests:
                        logger.info(f"Context updated: field={new_field}, interests={new_interests}")
                        return UserContext(
                            field=new_field,
                            interests=new_interests,
                            background=context.background,
                            constraints=context.constraints
                        )
                        
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse context extraction: {response}")
            
            return context
            
        except Exception as e:
            logger.error(f"Error updating context: {e}")
            return context

    def _has_enough_info(self, context: UserContext) -> bool:
        """Simple check: do we have field and some interests?"""
        return bool(context.field and context.interests)
    
    def _get_next_question(self, context: UserContext) -> str:
        """Get the next question we need to ask"""
        if not context.field:
            return "What field are you studying? (e.g., Computer Science, Biology, Psychology, etc.)"
        
        if not context.interests:
            return f"What specific areas within {context.field} interest you most?"
        
        # Fallback
        return "Could you tell me more about what kind of topics you're looking for?"
    
    def _generate_topics(self, user_input: str, context: UserContext) -> List[TopicSuggestion]:
        """Generate topic suggestions using Research Agent to find real papers"""
        try:
            if not self.research_tool:
                # Fallback to LLM-only generation if no research tool
                return self._generate_topics_llm_only(user_input, context)
            
            # Use research agent to find papers and generate research-backed topics
            interests = ", ".join(context.interests) if context.interests else "general research"
            search_query = f"{context.field} {interests}".strip()
            
            logger.info(f"Using Research Agent to find papers for: {search_query}")
            
            # Get papers from research agent
            papers = self.research_tool.collect_papers(search_query, max_results=30)
            
            if not papers:
                logger.warning(f"No papers found for {search_query}, falling back to LLM generation")
                return self._generate_topics_llm_only(user_input, context)
            
            # Use LLM to analyze papers and generate research-backed topics
            return self._generate_topics_from_papers(papers, context, user_input)
            
        except Exception as e:
            logger.error(f"Error generating topics with research: {e}")
            # Fallback to LLM-only generation
            return self._generate_topics_llm_only(user_input, context)
    
    def _parse_topics_from_response(self, response: str) -> List[TopicSuggestion]:
        """Parse topics from LLM response"""
        topics = []
        lines = response.split('\n')
        
        current_topic = None
        current_description = ""
        current_relevance = ""
        
        for line in lines:
            line = line.strip()
            
            # Look for topic titles (numbered or with **)
            if (line.startswith(('1.', '2.', '3.', '4.', '5.')) or 
                (line.startswith('**') and line.endswith('**'))):
                
                # Save previous topic
                if current_topic:
                    topics.append(TopicSuggestion(
                        title=current_topic,
                        description=current_description.strip(),
                        relevance=0.8,
                        why_relevant=current_relevance.strip(),
                        research_approach="Systematic research approach"
                    ))
                
                # Start new topic
                current_topic = line.replace('**', '').strip()
                # Remove numbering
                if current_topic and current_topic[0].isdigit():
                    current_topic = current_topic.split('.', 1)[1].strip()
                
                current_description = ""
                current_relevance = ""
            
            elif line.startswith('Relevant because:'):
                current_relevance = line.replace('Relevant because:', '').strip()
            
            elif line and current_topic and not line.startswith('Relevant because:'):
                if current_description:
                    current_description += " " + line
                else:
                    current_description = line
        
        # Don't forget the last topic
        if current_topic:
            topics.append(TopicSuggestion(
                title=current_topic,
                description=current_description.strip(),
                relevance=0.8,
                why_relevant=current_relevance.strip(),
                research_approach="Systematic research approach"
            ))
        
        return topics[:5]  # Limit to 5 topics
    
    def _generate_topics_from_papers(self, papers: List, context: UserContext, user_input: str) -> List[TopicSuggestion]:
        """Generate research-backed topics by analyzing real papers"""
        try:
            # Prepare paper summaries for LLM analysis
            paper_summaries = []
            for i, paper in enumerate(papers[:15]):  # Use top 15 papers
                summary = f"{i+1}. **{paper.title}** ({paper.year})\n   Authors: {', '.join(paper.authors[:3])}\n   Abstract: {paper.abstract[:200]}..."
                paper_summaries.append(summary)
            
            papers_text = "\n\n".join(paper_summaries)
            field = context.field or "the field"
            interests = ", ".join(context.interests) if context.interests else "the interests"
            
            prompt = f"""Based on these real research papers, generate 4 specific thesis topics for a student in {field} interested in {interests}.

Recent Research Papers:
{papers_text}

Requirements:
- Each topic should build on or extend the research shown in these papers
- Topics should be specific enough for a thesis (not too broad)
- Should identify research gaps or opportunities for novel contributions
- Must be feasible for a student to complete
- Should reference specific papers or research directions

For each topic, provide:
1. A clear, specific title
2. A brief description explaining the research opportunity
3. Which papers it builds on
4. Why it's a good thesis topic

Format as:

1. **Topic Title 1**
   Description of the research opportunity and approach.
   Builds on: Paper titles or research areas from the list above.
   Good thesis topic because: explanation

2. **Topic Title 2**
   Description of the research opportunity and approach.
   Builds on: Paper titles or research areas from the list above.
   Good thesis topic because: explanation

(continue for 4 topics)"""

            messages = [
                {"role": "system", "content": "You are an expert research advisor who identifies thesis opportunities from current literature."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.6, max_tokens=1000)
            
            if response:
                return self._parse_research_backed_topics(response, papers)
            
            return []
            
        except Exception as e:
            logger.error(f"Error generating topics from papers: {e}")
            return []

    def _parse_research_backed_topics(self, response: str, papers: List) -> List[TopicSuggestion]:
        """Parse research-backed topics from LLM response"""
        topics = []
        lines = response.split('\n')
        
        current_topic = None
        current_description = ""
        current_builds_on = ""
        current_why_good = ""
        
        for line in lines:
            line = line.strip()
            
            # Look for topic titles
            if (line.startswith(('1.', '2.', '3.', '4.', '5.')) or 
                (line.startswith('**') and line.endswith('**'))):
                
                # Save previous topic
                if current_topic:
                    # Find relevant papers for this topic
                    relevant_papers = self._find_relevant_papers(current_topic + " " + current_description, papers)
                    
                    topics.append(TopicSuggestion(
                        title=current_topic,
                        description=current_description.strip(),
                        relevance=0.9,  # High relevance since based on real research
                        why_relevant=current_why_good.strip(),
                        research_approach=current_builds_on.strip(),
                        sample_papers=relevant_papers[:3]  # Include top 3 relevant papers
                    ))
                
                # Start new topic
                current_topic = line.replace('**', '').strip()
                if current_topic and current_topic[0].isdigit():
                    current_topic = current_topic.split('.', 1)[1].strip()
                
                current_description = ""
                current_builds_on = ""
                current_why_good = ""
            
            elif line.startswith('Builds on:'):
                current_builds_on = line.replace('Builds on:', '').strip()
            elif line.startswith('Good thesis topic because:'):
                current_why_good = line.replace('Good thesis topic because:', '').strip()
            elif line and current_topic and not any(line.startswith(prefix) for prefix in ['Builds on:', 'Good thesis topic because:']):
                if current_description:
                    current_description += " " + line
                else:
                    current_description = line
        
        # Don't forget the last topic
        if current_topic:
            relevant_papers = self._find_relevant_papers(current_topic + " " + current_description, papers)
            topics.append(TopicSuggestion(
                title=current_topic,
                description=current_description.strip(),
                relevance=0.9,
                why_relevant=current_why_good.strip(),
                research_approach=current_builds_on.strip(),
                sample_papers=relevant_papers[:3]
            ))
        
        return topics[:4]  # Limit to 4 topics

    def _find_relevant_papers(self, topic_text: str, papers: List) -> List:
        """Find papers most relevant to a specific topic"""
        topic_words = set(topic_text.lower().split())
        scored_papers = []
        
        for paper in papers:
            # Simple relevance scoring based on word overlap
            paper_text = (paper.title + " " + paper.abstract).lower()
            paper_words = set(paper_text.split())
            
            overlap = len(topic_words.intersection(paper_words))
            score = overlap / len(topic_words) if topic_words else 0
            
            scored_papers.append((score, paper))
        
        # Sort by relevance score and return papers
        scored_papers.sort(key=lambda x: x[0], reverse=True)
        return [paper for score, paper in scored_papers]

    def _generate_topics_llm_only(self, user_input: str, context: UserContext) -> List[TopicSuggestion]:
        """Fallback method: Generate topics using only LLM knowledge"""
        try:
            field = context.field or "your field"
            interests = ", ".join(context.interests) if context.interests else "your interests"
            
            prompt = f"""Generate 3 specific, feasible thesis topics for a student.

Field: {field}
Interests: {interests}
User request: "{user_input}"

Requirements:
- Specific enough for a thesis (not too broad)
- Feasible for a student to complete
- Current and relevant
- Should allow for original contribution

For each topic, provide:
1. A clear, specific title
2. A brief description (2-3 sentences)
3. Why it's relevant to their interests

Format as a simple list:

1. **Topic Title 1**
   Description of the topic and its scope.
   Relevant because: explanation

2. **Topic Title 2**
   Description of the topic and its scope.
   Relevant because: explanation

(continue for 3 topics)"""

            messages = [
                {"role": "system", "content": "You are an expert academic advisor. Generate specific, feasible thesis topics."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.client.chat_completion(messages, temperature=0.7, max_tokens=800)
            
            if response:
                return self._parse_topics_from_response(response)
            
            return []
            
        except Exception as e:
            logger.error(f"Error generating topics with LLM only: {e}")
            return []

    def _validate_topics_with_research(self, topics: List[TopicSuggestion]) -> List[TopicSuggestion]:
        """Use research agent to validate topics"""
        validated_topics = []
        
        for topic in topics:
            try:
                if hasattr(self.research_tool, 'evaluate_topic'):
                    evaluation = self.research_tool.evaluate_topic(topic.title)
                    
                    # Only include topics with decent feasibility
                    if evaluation.feasibility_score > 0.3:
                        topic.research_validation = evaluation
                        validated_topics.append(topic)
                else:
                    # Research tool doesn't have evaluate_topic method
                    validated_topics.append(topic)
                    
            except Exception as e:
                logger.warning(f"Research validation failed for {topic.title}: {e}")
                # Include without validation if research fails
                validated_topics.append(topic)
        
        return validated_topics
    
    def _format_topics_for_user(self, topics: List[TopicSuggestion]) -> str:
        """Format topics for user presentation"""
        if not topics:
            return "I couldn't generate any suitable topics."
        
        message = f"I found {len(topics)} promising thesis topics for you:\n\n"
        
        for i, topic in enumerate(topics, 1):
            message += f"**{i}. {topic.title}**\n"
            message += f"{topic.description}\n"
            
            if topic.why_relevant:
                message += f"💡 Why relevant: {topic.why_relevant}\n"
            
            # Add research validation info if available
            if topic.research_validation:
                validation = topic.research_validation
                message += f"📊 Research feasibility: {validation.feasibility_score:.1f}/1.0 ({validation.paper_count} papers found)\n"
            
            message += "\n"
        
        message += "Would you like me to help you explore any of these topics further?"
        return message
    
    # Legacy methods for backward compatibility
    def suggest_topics(self, user_input: str, context: UserContext) -> TopicScoutResponse:
        """Legacy method - converts new response to old format"""
        response = self.process_request(user_input, context)
        
        if response.success and response.result:
            return TopicScoutResponse(
                success=True,
                result=response.result
            )
        elif response.instructions and len(response.instructions) > 0:
            # Extract first question from instructions
            first_instruction = response.instructions[0]
            return TopicScoutResponse(
                success=False,
                needs_info="context",
                message=first_instruction.message
            )
        else:
            return TopicScoutResponse(
                success=False,
                error_message=response.user_message or "Could not process request"
            )
    
    def respond(self, query: str) -> str:
        """Legacy method - creates basic context and calls process_request"""
        context = UserContext()
        response = self.process_request(query, context)
        return response.user_message or "I couldn't process your request."