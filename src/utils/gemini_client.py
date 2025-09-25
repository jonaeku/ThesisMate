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

    def chat_completion(
        self,
        messages,
        temperature: float = 0.0,
        max_tokens: int = 600,
        response_schema: dict | None = None,
        force_json: bool = False,
    ) -> str:
        # Messages in einen Prompt gießen (einfach, aber robust)
        parts = []
        for m in messages:
            role = m.get("role", "user")
            parts.append(f"{role.capitalize()}: {m.get('content','').strip()}")
        prompt = "\n".join(parts).strip()

        # Generation Config
        cfg_kwargs = dict(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        # JSON-Mode aktivieren, wenn Schema gegeben oder explizit gefordert
        if response_schema or force_json:
            cfg_kwargs["response_mime_type"] = "application/json"
        if response_schema:
            cfg_kwargs["response_schema"] = response_schema

        cfg = GenerationConfig(**cfg_kwargs)
        resp = self.model.generate_content(prompt, generation_config=cfg)

        # Text robust extrahieren
        text = getattr(resp, "text", None)
        if not text:
            # Fallback: aus Kandidaten lesen
            try:
                cand = resp.candidates[0]
                parts = getattr(cand, "content", {}).parts or []
                text = "".join(getattr(p, "text", "") for p in parts)
            except Exception:
                text = ""
        if not text or not text.strip():
            raise ValueError("Gemini returned empty response")
        return text.strip()
