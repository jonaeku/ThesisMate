#!/usr/bin/env python3
"""
Test the complete workflow: field → interests → topics
"""

import sys
sys.path.append('src')

from orchestrator.orchestrator import Orchestrator
from utils.logging import get_logger

logger = get_logger(__name__)

def test_complete_workflow():
    """Test the complete workflow"""
    print("🔄 Testing Complete Workflow")
    print("=" * 50)
    
    try:
        # Initialize Orchestrator
        orchestrator = Orchestrator()
        user_id = "test_workflow_user"
        
        # Step 1: Initial request
        print("\n📋 Step 1: Initial Request")
        print("-" * 30)
        query1 = "Can you help me find thesis topics?"
        result1 = orchestrator.run(query1, user_id=user_id)
        print(f"Query: {query1}")
        print(f"Response: {result1}")
        
        # Step 2: Provide field
        print("\n📚 Step 2: Provide Field")
        print("-" * 30)
        query2 = "Computer Science"
        result2 = orchestrator.run(query2, user_id=user_id)
        print(f"Query: {query2}")
        print(f"Response: {result2}")
        
        # Step 3: Provide specific interests
        print("\n🎯 Step 3: Provide Specific Interests")
        print("-" * 30)
        query3 = "AI in Healthcare and Multi-Agent Systems"
        result3 = orchestrator.run(query3, user_id=user_id)
        print(f"Query: {query3}")
        print(f"Response: {result3[:200]}...")
        
        print("\n✅ Complete workflow test finished!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_complete_workflow()
