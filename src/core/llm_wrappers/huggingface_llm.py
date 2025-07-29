import aiohttp
import os
from typing import Optional, List, Any
from .base_llm import BaseLLMWrapper
import logging

logger = logging.getLogger(__name__)

class HuggingFaceLLM(BaseLLMWrapper):
    api_token: str
    temperature: float = 0.7
    max_tokens: int = 2048
    use_cache: bool = True
    base_url: str = "https://api-inference.huggingface.co/models"
    
    def __init__(
        self,
        model_name: str = "meta-llama/Llama-2-7b-chat-hf",
        api_token: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        use_cache: bool = True,
        **kwargs
    ):
        if not api_token:
            api_token = os.getenv("HUGGINGFACE_API_TOKEN")
            if not api_token:
                raise ValueError("Hugging Face API token is required")
        
        # Filter out conflicting parameters
        filtered_kwargs = {k: v for k, v in kwargs.items() 
                          if k not in ['api_token', 'temperature', 'max_tokens', 'use_cache', 'base_url', 'timeout']}
        
        # Use timeout from kwargs if provided, otherwise use default
        timeout_value = kwargs.get('timeout', 60.0)
        
        super().__init__(
            model_name=model_name,
            environment="testing",
            api_token=api_token,
            temperature=temperature,
            max_tokens=max_tokens,
            use_cache=use_cache,
            base_url="https://api-inference.huggingface.co/models",
            timeout=timeout_value,
            **filtered_kwargs
        )
    
    async def _make_api_call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Make API call to Hugging Face Inference API"""
        
        # Prepare request payload
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": kwargs.get("temperature", self.temperature),
                "max_new_tokens": kwargs.get("max_tokens", self.max_tokens),
                "return_full_text": False,
                "do_sample": True,
            },
            "options": {
                "use_cache": self.use_cache,
                "wait_for_model": True,  # Wait if model is loading
            }
        }
        
        if stop:
            payload["parameters"]["stop_sequences"] = stop
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        
        # Make HTTP request
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            async with session.post(
                f"{self.base_url}/{self.model_name}",
                json=payload,
                headers=headers
            ) as response:
                
                # Handle rate limiting
                if response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    raise Exception(f"Rate limited. Retry after {retry_after} seconds")
                
                # Handle model loading
                if response.status == 503:
                    error_data = await response.json()
                    if "loading" in error_data.get("error", "").lower():
                        estimated_time = error_data.get("estimated_time", 30)
                        raise Exception(f"Model loading. Estimated time: {estimated_time}s")
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Hugging Face API error {response.status}: {error_text}")
                
                result = await response.json()
                
                # Handle different response formats
                if isinstance(result, list) and len(result) > 0:
                    if "generated_text" in result[0]:
                        return result[0]["generated_text"].strip()
                    elif "text" in result[0]:
                        return result[0]["text"].strip()
                
                # Handle error responses
                if isinstance(result, dict) and "error" in result:
                    raise Exception(f"Hugging Face error: {result['error']}")
                
                return str(result).strip()
    
    async def get_model_info(self) -> dict:
        """Get model information from Hugging Face"""
        headers = {"Authorization": f"Bearer {self.api_token}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://huggingface.co/api/models/{self.model_name}",
                headers=headers
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"Failed to get model info: {response.status}"}