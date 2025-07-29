from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from langchain.llms.base import LLM
from langchain.callbacks.manager import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
from src.config.settings import get_settings
import asyncio
import time
import logging
import concurrent.futures
import threading
from dataclasses import dataclass
import hashlib

logger = logging.getLogger(__name__)

@dataclass
class LLMMetrics:
    total_calls: int = 0
    total_tokens: int = 0
    total_latency: float = 0.0
    error_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

class BaseLLMWrapper(LLM, ABC):
    # Declare Pydantic fields
    model_name: str
    environment: str = "development"
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 30.0
    enable_caching: bool = True
    cache_max_size: int = 10
    metrics: LLMMetrics = None
    response_cache: Dict[str, str] = None
    """
    Simplified base class for LLM wrappers focusing on:
    - Retry logic with exponential backoff
    - Metrics collection
    - Response caching
    - Environment-aware configuration
    """
    
    def __init__(
        self,
        model_name: str,
        environment: str = "development",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 30.0,
        enable_caching: bool = True,
        **kwargs
    ):
        filtered_kwargs = {k: v for k, v in kwargs.items() 
                          if k not in ['model_name', 'environment', 'max_retries', 'retry_delay', 'timeout', 'enable_caching']}
        
        super().__init__(
            model_name=model_name,
            environment=environment,
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout=timeout,
            enable_caching=enable_caching,
            **filtered_kwargs
        )
        
        if self.metrics is None:
            self.metrics = LLMMetrics()
        self._initialize_cache()

    def _initialize_cache(self):
        settings = get_settings()
        if settings.LLM_CACHE_ENABLED and self.enable_caching:
            self.response_cache = {}
            self.cache_max_size = settings.LLM_CACHE_MAX_SIZE
        else:
            self.response_cache = None
            self.cache_max_size = 0
            logger.debug(f"Cache disabled for {self.model_name}")


    @property
    def _llm_type(self) -> str:
        return f"{self.__class__.__name__.lower()}"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Synchronous call wrapper - simplified for testing"""
        try:
            nest_asyncio.apply()
        except:
            pass
        
        try:
            return asyncio.run(self._acall(prompt, stop, run_manager, **kwargs))
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e):
                # We're in an async context, use a different approach
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(
                            self._acall(prompt, stop, run_manager, **kwargs)
                        )
                    finally:
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    return future.result()
            else:
                raise
            
    async def _acall(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        # check cache first
        cache_key = self._generate_cache_key(prompt, stop, kwargs)
        if self.response_cache is not None and cache_key in self.response_cache:
            self.metrics.cache_hits +=1
            logger.debug(f"Cache hit for model {self.model_name}")
            return self.response_cache[cache_key]

        if self.response_cache is not None:
            self.metrics.cache_misses += 1

        # retry logic with exponential backoff
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                start_time = time.time()

                response = await self._make_api_call(prompt, stop, **kwargs)
                # track metrics
                latency = time.time() - start_time

                self._update_metrics(response, latency, success=True)

                # store in bounded cache
                self._cache_response(cache_key, response)

                logger.debug(f"Successful call to {self.model_name} in {latency:.2f}s")

                return response

            except Exception as e:
                last_exception = e
                self.metrics.error_count += 1
                self._update_metrics("", 0, success=False)

                logger.warning(f"Attempt {attempt + 1} failed for {self.model_name}: {str(e)}")

                # no retry on last attempt
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All retry attempts failed for {self.model_name}")
                    break

        # let model fallback chain handle failure
        raise last_exception


    def _cache_response(self, cache_key: str, response: str):
        if self.response_cache is None:
            return
        if self.cache_max_size > 0 and len(self.response_cache) >= self.cache_max_size:
            # Remove the first (oldest) entry
            oldest_key = next(iter(self.response_cache))
            del self.response_cache[oldest_key]
            logger.debug(f"Cache evicted oldest entry: {oldest_key[:5]}...")
        
        # Add new entry
        self.response_cache[cache_key] = response
        logger.debug(f"Cache stored: {cache_key[:5]}... (total: {len(self.response_cache)})")

    @abstractmethod
    async def _make_api_call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        pass

    def _generate_cache_key(self, prompt: str, stop: Optional[List[str]], kwargs: Dict) -> str:
        key_data = f"{prompt}_{stop}_{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _update_metrics(self, response: str, latency: float, success: bool):
        self.metrics.total_calls +=1
        if success:
            self.metrics.total_latency += latency
            self.metrics.total_tokens += len(response.split())

    def get_metrics(self) -> Dict[str, Any]:
        successful_calls = max(0, self.metrics.total_calls - self.metrics.error_count)
        avg_latency = (self.metrics.total_latency / max(1, successful_calls)) if successful_calls > 0 else 0.0

        total_cache_requests = self.metrics.cache_hits + self.metrics.cache_misses
        cache_hit_rate = (self.metrics.cache_hits / max(1, total_cache_requests)) if total_cache_requests > 0 else 0.0
        
        metrics = {
            "model_name": self.model_name,
            "environment": self.environment,
            "total_calls": self.metrics.total_calls,
            "successful_calls": successful_calls,
            "total_tokens": self.metrics.total_tokens,
            "average_latency": avg_latency,
            "error_count": self.metrics.error_count,
            "error_rate": (self.metrics.error_count / max(1, self.metrics.total_calls)),
            "cache_hits": self.metrics.cache_hits,
            "cache_misses": self.metrics.cache_misses,
            "cache_hit_rate": cache_hit_rate
        }

        if self.response_cache is not None:
            metrics["cache_size"] = len(self.response_cache)
            metrics["cache_max_size"] = self.cache_max_size

        return metrics

    def clear_cache(self):
        if self.response_cache is not None:
            self.response_cache.clear()
            logger.info(f"Cache cleared for model {self.model_name}")


