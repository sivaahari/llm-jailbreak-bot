import aiohttp
import asyncio
import logging
from typing import Optional

from config import OLLAMA_HOST, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)

class OllamaError(Exception):
    pass

async def generate(
    model: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 800,
    format: Optional[str] = None  # Added format parameter
) -> str:
    url = f"{OLLAMA_HOST}/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        }
    }
    
    if system_prompt:
        payload["system"] = system_prompt
        
    if format == "json":
        payload["format"] = "json"
    
    timeout = aiohttp.ClientTimeout(total=OLLAMA_TIMEOUT)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise OllamaError(f"HTTP {response.status}: {error_text}")
                
                data = await response.json()
                return data.get("response", "").strip()
                
    except Exception as e:
        logger.error(f"Generate error for model {model}: {e}")
        raise OllamaError(f"Request failed: {str(e)}")