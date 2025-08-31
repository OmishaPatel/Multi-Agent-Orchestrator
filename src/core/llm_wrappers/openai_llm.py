import aiohttp
import os
import uuid
import time
from typing import Optional, List, Any, Dict
from .base_llm import BaseLLMWrapper
import logging
from src.services.langfuse_service import langfuse_service

logger = logging.getLogger(__name__)

class OpenAILLM(BaseLLMWrapper):
    """
    LLM wrapper for OpenAI API - reliable alternative to HuggingFace
    """
    api_token: str
    temperature: float = 0.7
    max_tokens: int = 2048
    base_url: str = "https://api.openai.com/v1"
    request_timeout: float = 120.0
    request_count: int = 0
    last_request_time: Optional[float] = None
    
    def __init__(
        self,
        model_name: str = "gpt-3.5-turbo",
        api_token: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        request_timeout: float = 120.0,
        **kwargs
    ):
        if not api_token:
            api_token = os.getenv("OPENAI_API_KEY")
            if not api_token:
                raise ValueError("OpenAI API token is required")
        
        # Get environment from kwargs or default to testing
        environment = kwargs.get('environment', 'testing')
        
        # Filter out conflicting parameters
        filtered_kwargs = {k: v for k, v in kwargs.items() 
                          if k not in ['api_token', 'temperature', 'max_tokens', 'base_url', 'timeout', 'request_timeout', 'environment']}
        
        super().__init__(
            model_name=model_name,
            environment=environment,
            api_token=api_token,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url="https://api.openai.com/v1",
            timeout=request_timeout,  # Map request_timeout to timeout for base class
            **filtered_kwargs
        )
    
    async def _make_api_call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Make API call to OpenAI"""

        request_id = str(uuid.uuid4())
        self.request_count += 1
        self.last_request_time = time.time()
        
        # Use chat completions format
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }
        
        if stop:
            payload["stop"] = stop
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "X-Request-ID": request_id
        }
        
        try: 
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                ) as response:
                    
                    if response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        raise Exception(f"Rate limited. Retry after {retry_after} seconds")
                    
                    if response.status == 401:
                        raise Exception("Invalid OpenAI API token")
                    
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"OpenAI API error {response.status}: {error_text}")
                    
                    result = await response.json()
                    response_text = result["choices"][0]["message"]["content"].strip()

                    # Model usage tracking is now handled by the base class

                    logger.info(f"Successfully received response from {self.model_name}")
                    return response_text

        except aiohttp.ClientError as e:
            raise Exception(f"Network error connecting to OpenAI API: {str(e)}")
        except Exception as e:
            if "OpenAI" not in str(e):
                raise Exception(f"OpenAI API call failed: {str(e)}")
            raise
    
    def _calculate_input_cost(self, input_tokens: int) -> float:
        """Calculate input cost based on model and token count"""
        # OpenAI pricing (as of 2024) - update these as needed
        pricing = {
            "gpt-3.5-turbo": 0.0015 / 1000,  # $0.0015 per 1K tokens
            "gpt-4": 0.03 / 1000,            # $0.03 per 1K tokens
            "gpt-4-turbo": 0.01 / 1000,      # $0.01 per 1K tokens
        }
        rate = pricing.get(self.model_name, 0.0015 / 1000)  # Default to GPT-3.5 rate
        return input_tokens * rate

    def _calculate_output_cost(self, output_tokens: int) -> float:
        """Calculate output cost based on model and token count"""
        # OpenAI pricing (as of 2024) - update these as needed
        pricing = {
            "gpt-3.5-turbo": 0.002 / 1000,   # $0.002 per 1K tokens
            "gpt-4": 0.06 / 1000,            # $0.06 per 1K tokens
            "gpt-4-turbo": 0.03 / 1000,      # $0.03 per 1K tokens
        }
        rate = pricing.get(self.model_name, 0.002 / 1000)  # Default to GPT-3.5 rate
        return output_tokens * rate

    async def _acall(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> str:
        """
        Async call implementation with enhanced Langfuse integration
        """
        # The Langfuse callback handler will automatically capture this call
        # when used within a LangGraph workflow
        return await super()._acall(prompt, stop, run_manager, **kwargs)