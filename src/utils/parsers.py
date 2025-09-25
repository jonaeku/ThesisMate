from typing import Any
from langchain_core.messages import AIMessage
from src.models.models import NeedsInfo, OutlineSection

def parse_payload(msg: AIMessage) -> Any:
    """
    Liest strukturierte Payloads aus AIMessage:
    - additional_kwargs["data_type"] == "needs_info" | "outline"
    - content enthält JSON-String der Pydantic-Instanz
    """
    kind = (msg.additional_kwargs or {}).get("data_type")
    if kind == "needs_info":
        return NeedsInfo.model_validate_json(msg.content)
    if kind == "outline":
        return OutlineSection.model_validate_json(msg.content)
    return msg.content  # Plaintext-Fallback
