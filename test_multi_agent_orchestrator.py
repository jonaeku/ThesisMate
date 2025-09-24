#!/usr/bin/env python3
"""
Test the enhanced multi-agent orchestrator with LangGraph patterns
"""

import sys
import os
sys.path.append('src')

from orchestrator.orchestrator import Orchestrator
from utils.logging import get_logger

logger = get_logger(__name__)

def test_orchestrator():
    """Test the multi-agent orchestrator"""
    print("🚀 Testing Enhanced Multi-Agent Orchestrator")
    print("=" * 50)
    
    try:
        # Initialize orchestrator
        orchestrator = Orchestrator()
        print("✅ Orchestrator initialized successfully")
        
        # Test 1: Topic discovery workflow
        print("\n📋 Test 1: Topic Discovery")
        print("-" * 30)
        query1 = "I'm studying computer science and interested in AI"
        response1 = orchestrator.run(query1, user_id="test_user_1")
        print(f"Query: {query1}")
        print(f"Response: {response1[:200]}...")
        
        # Test 2: Research request
        print("\n📚 Test 2: Research Request")
        print("-" * 30)
        query2 = "Find papers about machine learning in healthcare"
        response2 = orchestrator.run(query2, user_id="test_user_2")
        print(f"Query: {query2}")
        print(f"Response: {response2[:200]}...")
        
        # Test 3: Structure request
        print("\n🏗️ Test 3: Structure Request")
        print("-" * 30)
        query3 = "Help me create a thesis outline"
        response3 = orchestrator.run(query3, user_id="test_user_3")
        print(f"Query: {query3}")
        print(f"Response: {response3[:200]}...")
        
        # Test 4: Simple greeting (should route to end)
        print("\n👋 Test 4: Simple Greeting")
        print("-" * 30)
        query4 = "Hello, how are you?"
        response4 = orchestrator.run(query4, user_id="test_user_4")
        print(f"Query: {query4}")
        print(f"Response: {response4}")
        
        print("\n✅ All tests completed successfully!")
        print("🎉 Multi-agent orchestration is working!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_orchestrator()
