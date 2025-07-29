import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.core.llm_wrappers.base_llm import BaseLLMWrapper

class TestBaseLLMWrapper(BaseLLMWrapper):
    """Test implementation of BaseLLMWrapper"""
    call_count: int = 0
    should_fail_until: int = 0
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    async def _make_api_call(self, prompt: str, stop=None, **kwargs):
        # Mock implementation for testing
        self.call_count += 1
        
        # Support for retry testing
        if self.should_fail_until > 0 and self.call_count <= self.should_fail_until:
            raise Exception("Temporary failure")
        
        if "error" in prompt.lower():
            raise Exception("Simulated API error")
        if "timeout" in prompt.lower():
            await asyncio.sleep(0.1)  # Simulate timeout
            raise Exception("Request timeout")
        
        # Add small delay to simulate API call time
        await asyncio.sleep(0.001)
        return f"Response to: {prompt}"

@pytest.mark.asyncio
class TestBaseLLMWrapperFunctionality:
    
    async def test_successful_call(self):
        """Test successful LLM call"""
        llm = TestBaseLLMWrapper(model_name="test-model")
        
        response = await llm._acall("Hello, world!")
        
        assert response == "Response to: Hello, world!"
        assert llm.metrics.total_calls == 1
        assert llm.metrics.error_count == 0
    
    async def test_retry_logic_with_eventual_success(self):
        """Test retry logic with eventual success"""
        llm = TestBaseLLMWrapper(model_name="test-model", max_retries=2, retry_delay=0.01)
        llm.should_fail_until = 1  # Fail on first call, succeed on second
        
        response = await llm._acall("Hello, world!")
        
        assert response == "Response to: Hello, world!"
        assert llm.call_count == 2
        assert llm.metrics.error_count == 1  # One failure before success
        assert llm.metrics.total_calls == 2  # All attempts counted
    
    async def test_retry_logic_all_failures(self):
        """Test retry logic when all attempts fail"""
        llm = TestBaseLLMWrapper(
            model_name="test-model",
            max_retries=2,
            retry_delay=0.01
        )
        
        with pytest.raises(Exception, match="Simulated API error"):
            await llm._acall("error prompt")
        
        # Should have tried 3 times (initial + 2 retries)
        assert llm.metrics.error_count == 3
        assert llm.metrics.total_calls == 3
    
    async def test_exponential_backoff_timing(self):
        """Test that exponential backoff increases delay"""
        llm = TestBaseLLMWrapper(
            model_name="test-model",
            max_retries=2,
            retry_delay=0.1
        )
        
        start_time = asyncio.get_event_loop().time()
        
        with pytest.raises(Exception):
            await llm._acall("error prompt")
        
        end_time = asyncio.get_event_loop().time()
        
        # Should have delays of 0.1s and 0.2s = 0.3s minimum
        assert end_time - start_time >= 0.25  # Allow some tolerance
    
    async def test_caching_functionality(self):
        """Test response caching"""
        llm = TestBaseLLMWrapper(model_name="test-model", enable_caching=True)
        
        # First call
        response1 = await llm._acall("Hello, world!")
        
        # Second call should hit cache (no additional API call)
        response2 = await llm._acall("Hello, world!")
        
        assert response1 == response2
        assert llm.metrics.total_calls == 1  # Only one actual API call
    
    async def test_caching_disabled(self):
        """Test behavior when caching is disabled"""
        llm = TestBaseLLMWrapper(model_name="test-model", enable_caching=False)
        
        # Two calls should both hit the API
        response1 = await llm._acall("Hello, world!")
        response2 = await llm._acall("Hello, world!")
        
        assert response1 == response2
        assert llm.metrics.total_calls == 2  # Two API calls
    
    async def test_cache_key_generation(self):
        """Test that different prompts generate different cache keys"""
        llm = TestBaseLLMWrapper(model_name="test-model", enable_caching=True)
        
        await llm._acall("Hello, world!")
        await llm._acall("Goodbye, world!")
        
        assert llm.metrics.total_calls == 2  # Two different prompts = two API calls
    
    def test_metrics_collection(self):
        """Test metrics collection and calculation"""
        llm = TestBaseLLMWrapper(model_name="test-model")
        
        metrics = llm.get_metrics()
        
        expected_keys = [
            "model_name", "environment", "total_calls", "successful_calls",
            "total_tokens", "average_latency", "error_count", "error_rate"
        ]
        
        for key in expected_keys:
            assert key in metrics
        
        assert metrics["model_name"] == "test-model"
        assert metrics["environment"] == "development"
        assert metrics["total_calls"] == 0
        assert metrics["error_rate"] == 0.0
    
    async def test_metrics_after_successful_calls(self):
        """Test metrics after successful API calls"""
        llm = TestBaseLLMWrapper(model_name="test-model")
        
        await llm._acall("Hello, world!")
        await llm._acall("How are you?")
        
        metrics = llm.get_metrics()
        
        assert metrics["total_calls"] == 2
        assert metrics["successful_calls"] == 2
        assert metrics["error_count"] == 0
        assert metrics["error_rate"] == 0.0
        assert metrics["total_tokens"] > 0  # Should have counted tokens
        assert metrics["average_latency"] > 0  # Should have measured latency
    
    async def test_metrics_after_failed_calls(self):
        """Test metrics after failed API calls"""
        llm = TestBaseLLMWrapper(model_name="test-model", max_retries=1)
        
        with pytest.raises(Exception):
            await llm._acall("error prompt")
        
        metrics = llm.get_metrics()
        
        assert metrics["total_calls"] == 2  # Initial + 1 retry
        assert metrics["successful_calls"] == 0
        assert metrics["error_count"] == 2
        assert metrics["error_rate"] == 1.0
    
    def test_synchronous_call_wrapper(self):
        """Test that synchronous _call method works"""
        llm = TestBaseLLMWrapper(model_name="test-model")
        
        response = llm._call("Hello, world!")
        
        assert response == "Response to: Hello, world!"
        assert llm.metrics.total_calls == 1
