# src/utils/gemini_client.py
import os
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

class GeminiClient:
    def __init__(self, model: str = "gemini-1.5-flash"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

    def chat_completion(self, messages, temperature: float = 0.0, max_tokens: int = 600) -> str:
        # Prompt zusammenbauen
        parts = []
        for m in messages:
            role = m.get("role", "user")
            parts.append(f"{role.capitalize()}: {m.get('content','').strip()}")
        prompt = "\n".join(parts).strip()

        # Minimales Schema (nur erlaubte Felder)
        response_schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["title", "description"]
            }
        }

        cfg = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_schema=response_schema,
        )

        resp = self.model.generate_content(prompt, generation_config=cfg)
        out = resp.text if isinstance(resp.text, str) else None
        if not out or not out.strip():
            raise ValueError("Gemini returned empty JSON response")
        return out.strip()
