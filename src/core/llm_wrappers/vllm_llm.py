import aiohttp
import json
import os
from typing import Optional, List, Any, Dict
from .base_llm import BaseLLMWrapper
from ...config.model_environment import Environment as ModelEnvironment

class vLLMLLM(BaseLLMWrapper):
  
    base_url: str = "http://localhost:8000"
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    enable_batching: bool = True
    batch_size: int = 4
    pending_requests: List[Dict] = None
    
    def __init__(
        self,
        model_name: str = "meta-llama/Llama-2-7b-chat-hf",
        base_url: str = "http://localhost:8000",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        **kwargs
    ):
        # Get timeout from kwargs or use default
        timeout = kwargs.pop('timeout', 45.0)
        # Get environment from kwargs or use default
        environment = kwargs.pop('environment', ModelEnvironment.PRODUCTION.value)
        
        super().__init__(
            model_name=model_name,
            environment=environment,
            timeout=timeout,
            base_url=base_url.rstrip('/'),
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            enable_batching=True,
            batch_size=4,
            **kwargs
        )
        
        if self.pending_requests is None:
            self.pending_requests = []
    
    async def _make_api_call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        
        # Prepare request payload (OpenAI format)
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "top_p": kwargs.get("top_p", self.top_p),
            "frequency_penalty": kwargs.get("frequency_penalty", self.frequency_penalty),
            "presence_penalty": kwargs.get("presence_penalty", self.presence_penalty),
            "stream": False,
        }
        
        if stop:
            payload["stop"] = stop
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_api_key()}"  # Optional auth
        }
        
        # Make HTTP request to vLLM server
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
            async with session.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"vLLM API error {response.status}: {error_text}")
                
                result = await response.json()
                
                # Handle OpenAI-compatible response format
                if "choices" in result and len(result["choices"]) > 0:
                    choice = result["choices"][0]
                    if "message" in choice:
                        return choice["message"]["content"].strip()
                    elif "text" in choice:
                        return choice["text"].strip()
                
                # Handle error responses
                if "error" in result:
                    raise Exception(f"vLLM error: {result['error']['message']}")
                
                raise Exception(f"Unexpected vLLM response format: {result}")
    
    def _get_api_key(self) -> str:
        """Get API key for vLLM server (if authentication is enabled)"""
        return os.getenv("VLLM_API_KEY", "dummy-key")
    
    async def check_server_health(self) -> Dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                # Check health endpoint
                async with session.get(f"{self.base_url}/health") as response:
                    health_status = await response.json() if response.status == 200 else {"status": "unhealthy"}
                
                # Check models endpoint
                async with session.get(f"{self.base_url}/v1/models") as response:
                    models_info = await response.json() if response.status == 200 else {"data": []}
                
                return {
                    "health": health_status,
                    "models": models_info,
                    "server_url": self.base_url,
                    "model_available": any(
                        model.get("id") == self.model_name 
                        for model in models_info.get("data", [])
                    )
                }
        except Exception as e:
            return {
                "health": {"status": "error", "error": str(e)},
                "models": {"data": []},
                "server_url": self.base_url,
                "model_available": False
            }
    
    async def get_server_stats(self) -> Dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/stats") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"error": f"Stats unavailable: {response.status}"}
        except Exception as e:
            return {"error": f"Failed to get stats: {str(e)}"}
