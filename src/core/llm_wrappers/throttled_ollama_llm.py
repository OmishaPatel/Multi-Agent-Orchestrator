import asyncio
from typing import Optional, List, Any
from .ollama_llm import OllamaLLM
import logging

logger = logging.getLogger(__name__)

class ThrottledOllamaLLM(OllamaLLM):
    """
    Ollama LLM wrapper with request throttling to prevent concurrent request issues
    """
    
    # Class-level semaphore to limit concurrent requests across all instances
    _request_semaphore = asyncio.Semaphore(1)
    _request_delay = 0.1  # Small delay between requests
    
    async def _make_api_call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:     
        # Acquire semaphore to ensure only one request at a time
        async with self._request_semaphore:
            try:
                # Small delay to prevent rapid-fire requests
                await asyncio.sleep(self._request_delay)
                
                # Call parent implementation with validation
                result = await super()._make_api_call(prompt, stop, **kwargs)
                
                # Validate response is not empty
                if not result or result.strip() == "":
                    logger.warning(f"Empty response from {self.model_name}, retrying...")
                    raise Exception("Empty response from model")
                
                logger.debug(f"Throttled request completed for {self.model_name}")
                return result
                
            except Exception as e:
                logger.warning(f"Throttled request failed for {self.model_name}: {e}")
                # Add a longer delay before retrying to let Ollama recover
                await asyncio.sleep(1.0)
                raise