import pytest
from src.orchestrator.orchestrator import Orchestrator


def def test_orchestrator_run():
    orchestrator = Orchestrator()
    # This is a basic test and will fail for now
    result = orchestrator.run("AI")
    assert result is not None
