#!/usr/bin/env python3
"""
Simple test for Topic Scout Agent with Research Agent tool integration
"""

from src.agents.research import ResearchAgent
from src.agents.topic_scout import TopicScoutAgent
from src.models.models import UserContext

def test_topic_scout_workflow():
    """Test the complete Topic Scout workflow"""
    
    # Initialize agents
    research_agent = ResearchAgent()
    topic_scout = TopicScoutAgent(research_tool=research_agent)
    
    print("=== Topic Scout Integration Test ===\n")
    
    # Test 1: No context - should ask for field
    print("Test 1: User asks for help without context")
    context = UserContext()
    response = topic_scout.suggest_topics("Hilf mir bei der Themenfindung", context)
    
    print(f"Success: {response.success}")
    print(f"Needs info: {response.needs_info}")
    print(f"Message: {response.message}")
    print()
    
    # Test 2: Provide field - should ask for interests
    print("Test 2: User provides field")
    context = UserContext(field="Informatik")
    response = topic_scout.suggest_topics("Ich studiere Informatik", context)
    
    print(f"Success: {response.success}")
    print(f"Needs info: {response.needs_info}")
    print(f"Message: {response.message}")
    print()
    
    # Test 3: Provide interests - should generate topics
    print("Test 3: User provides interests")
    context = UserContext(field="Informatik", interests=["KI", "Machine Learning"])
    response = topic_scout.suggest_topics("KI und Machine Learning interessieren mich", context)
    
    print(f"Success: {response.success}")

    if response.success:
        print(response)
        # print(f"Found {len(response.result)} topics:")
        # for i, topic in enumerate(response.result, 1):
        #     print(f"\n  **{i}. {topic.title}**")
        #     print(f"     📊 Feasibility: {topic.relevance:.2f} | 📚 Papers: {len(topic.sample_papers)}")
        #     print(f"     💡 Why: {topic.why_relevant}")
        #     print(f"     🔬 Approach: {topic.research_approach}")
        #     if topic.sample_papers:
        #         print(f"     📄 Sample Papers:")
        #         for j, paper in enumerate(topic.sample_papers[:2], 1):
        #             print(f"        {j}. {paper.title[:60]}... ({paper.year})")
        #             if paper.url:
        #                 print(f"           Link: {paper.url}")
    else:
        print(f"Error: {response.error_message}")
    print()

if __name__ == "__main__":
    test_topic_scout_workflow()
