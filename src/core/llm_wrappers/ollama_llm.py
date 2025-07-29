import aiohttp
import json
from typing import Optional, List, Any
from .base_llm import BaseLLMWrapper
import logging

logger = logging.getLogger(__name__)

class OllamaLLM(BaseLLMWrapper):
    """
    LangChain wrapper for Ollama local models
    Optimized for development environment with lightweight models
    """
    
    # Pydantic field declarations
    base_url: str = "http://localhost:11434"
    temperature: float = 0.7
    max_tokens: int = 2048
    
    def __init__(
        self,
        model_name: str = "phi3:mini",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs
    ):
        # Filter out conflicting parameters
        filtered_kwargs = {k: v for k, v in kwargs.items() 
                          if k not in ['base_url', 'temperature', 'max_tokens']}
        
        super().__init__(
            model_name=model_name,
            environment="development",
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            **filtered_kwargs
        )
        
    async def _make_api_call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        
        # Prepare request payload
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.temperature),
                "num_predict": kwargs.get("max_tokens", self.max_tokens),
            }
        }
        
        if stop:
            payload["options"]["stop"] = stop
        
        # Make HTTP request to Ollama API
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")
                
                result = await response.json()
                
                if "error" in result:
                    raise Exception(f"Ollama error: {result['error']}")
                
                return result.get("response", "").strip()
    
    async def check_model_availability(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    if response.status == 200:
                        models = await response.json()
                        available_models = [model["name"] for model in models.get("models", [])]
                        return self.model_name in available_models
        except Exception as e:
            logger.warning(f"Failed to check Ollama model availability: {e}")
        
        return False
    
    async def pull_model_if_needed(self) -> bool:
        if await self.check_model_availability():
            return True
        
        logger.info(f"Pulling Ollama model: {self.model_name}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/pull",
                    json={"name": self.model_name}
                ) as response:
                    if response.status == 200:
                        # Stream the pull progress (simplified)
                        async for line in response.content:
                            if line:
                                try:
                                    progress = json.loads(line.decode())
                                    if progress.get("status") == "success":
                                        logger.info(f"Successfully pulled {self.model_name}")
                                        return True
                                except json.JSONDecodeError:
                                    continue
        except Exception as e:
            logger.error(f"Failed to pull Ollama model {self.model_name}: {e}")
        
        return False