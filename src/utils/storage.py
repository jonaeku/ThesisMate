import json
import os
from typing import List, Optional
from src.models.models import Paper, ConversationState

def ensure_data_dir():
    """Create data directory if it doesn't exist"""
    os.makedirs("data", exist_ok=True)

def save_papers(papers: List[Paper], filename: str = "data/papers.json"):
    """Save papers to JSON file"""
    ensure_data_dir()
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump([paper.model_dump() for paper in papers], f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving papers: {e}")
        return False

def load_papers(filename: str = "data/papers.json") -> List[Paper]:
    """Load papers from JSON file"""
    if not os.path.exists(filename):
        return []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [Paper(**item) for item in data]
    except Exception as e:
        print(f"Error loading papers: {e}")
        return []

def save_conversation_state(state: ConversationState, filename: str = "data/conversation.json"):
    """Save conversation state so Topic Scout remembers the chat"""
    ensure_data_dir()
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(state.model_dump(), f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving conversation: {e}")
        return False

def load_conversation_state(filename: str = "data/conversation.json") -> Optional[ConversationState]:
    """Load conversation state so Topic Scout can continue the chat"""
    if not os.path.exists(filename):
        return ConversationState()  # Return empty state if no file
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return ConversationState(**data)
    except Exception as e:
        print(f"Error loading conversation: {e}")
        return ConversationState()

def export_bibtex(papers: List[Paper]) -> str:
    """Export papers to BibTeX format"""
    bibtex_entries = []
    for paper in papers:
        if paper.bibtex:
            bibtex_entries.append(paper.bibtex)
    
    return "\n\n".join(bibtex_entries)
