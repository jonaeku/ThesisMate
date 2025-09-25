# src/utils/openrouter_client.py
import time
import threading
import requests
from typing import Dict, Any, Optional, List
from src.utils.config import get_env
from src.utils.custom_logging import get_logger

logger = get_logger(__name__)

# Schema: JSON-Array([{title, description}])
_JSON_ARRAY_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "Subsections",
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["title", "description"]
            }
        },
        "strict": True
    }
}

class OpenRouterClient:
    def __init__(self):
        self.api_key = get_env("OPENROUTER_API_KEY")
        self.model = get_env("OPENROUTER_MODEL")
        self.base_url = get_env("OPENROUTER_BASE_URL")  # z.B. https://openrouter.ai/api/v1
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo/thesismate",
            "X-Title": "ThesisMate"
        }
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._min_interval = 1.2

    def _should_force_json(self, messages: List[Dict[str, str]]) -> bool:
        for m in messages:
            if m.get("role") == "system":
                c = (m.get("content") or "").lower()
                if "json api" in c or "only return json" in c or "only return json arrays" in c:
                    return True
        return False

    def chat_completion(
        self,
        messages: list[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        response_format: Optional[Dict[str, Any]] = None,
        retries: int = 2,
        retry_delay_s: float = 0.6,
    ) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        # JSON-Ausgabe erzwingen, falls System-Message das verlangt
        if response_format is not None:
            payload["response_format"] = response_format
        elif self._should_force_json(messages):
            payload["response_format"] = _JSON_ARRAY_SCHEMA

        attempt = 0
        while True:
            attempt += 1
            logger.info(f"Sending request to OpenRouter with model: {self.model}")
            logger.info(f"Payload: {payload}")

            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=45.0
            )
            logger.info(f"Response status: {resp.status_code}")
            logger.info(f"Response headers: {resp.headers}")

            # Retry bei 429
            if resp.status_code == 429 and attempt <= retries:
                logger.warning(f"429 from provider. Retrying attempt {attempt}/{retries} after {retry_delay_s}s.")
                time.sleep(retry_delay_s)
                continue

            if resp.status_code >= 400:
                raise RuntimeError(f"OpenRouter HTTP {resp.status_code}: {resp.text}")

            data = resp.json()
            logger.info(f"Response JSON: {data}")

            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ValueError(f"Unexpected response format: {data}")

            msg = choices[0].get("message", {})
            content = msg.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError(f"Unexpected/empty message content: {msg}")

            logger.info(f"Extracted content: {content[:400]}{'...' if len(content)>400 else ''}")
            return content.strip()
