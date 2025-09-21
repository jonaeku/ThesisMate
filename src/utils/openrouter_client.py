import requests
from typing import Dict, Any, Optional
from src.utils.config import get_env
from src.utils.custom_logging import get_logger

logger = get_logger(__name__)

class OpenRouterClient:
    def __init__(self):
        self.api_key = get_env("OPENROUTER_API_KEY")
        self.model = get_env("OPENROUTER_MODEL")
        self.base_url = get_env("OPENROUTER_BASE_URL")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo/thesismate",
            "X-Title": "ThesisMate"
        }
    
    def chat_completion(
        self, 
        messages: list[Dict[str, str]], 
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Optional[str]:
        """
        Send a chat completion request to OpenRouter
        """
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            logger.info(f"Sending request to OpenRouter with model: {self.model}")
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=30.0
            )
            
            response.raise_for_status()
            result = response.json()
            
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            else:
                logger.error(f"Unexpected response format: {result}")
                return None
                
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error calling OpenRouter API: {str(e)}")
            return None
