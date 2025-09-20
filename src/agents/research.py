from src.models.models import ResearchSummary
from src.utils.logging import get_logger

logger = get_logger(__name__)

class ResearchAgent:
    def respond(self, topic: str) -> list[ResearchSummary]:
        # Placeholder implementation
        return [
            ResearchSummary(title="Attention Is All You Need", authors=["Ashish Vaswani", "et al."], publication_year=2017, summary="The paper that introduced the Transformer architecture.", url="https://arxiv.org/abs/1706.03762"),
            ResearchSummary(title="Mastering the game of Go with deep neural networks and tree search", authors=["David Silver", "et al."], publication_year=2016, summary="The paper on AlphaGo.", url="https://www.nature.com/articles/nature16961"),
        ]
