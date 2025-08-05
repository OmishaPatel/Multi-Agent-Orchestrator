import pytest
import os
from dotenv import load_dotenv
from src.core.llm_wrappers.llm_factory import LLMFactory, AgentType, ModelEnvironment
from src.core.llm_wrappers.ollama_llm import OllamaLLM
from typing import Optional, List, Any

load_dotenv()

@pytest.mark.integration
@pytest.mark.asyncio
class TestLLMIntegration:
    """Integration tests for LLM wrappers (requires actual services)"""
    
    @pytest.mark.skipif(
        not os.getenv("TEST_OLLAMA", "").lower() == "true",
        reason="Ollama integration tests disabled"
    )
    async def test_ollama_end_to_end(self):
        """Test complete Ollama workflow"""
        llm = LLMFactory.create_llm(
            AgentType.PLANNING,
            ModelEnvironment.DEVELOPMENT
        )
        
        # Check if model is available
        if hasattr(llm, 'check_model_availability'):
            available = await llm.check_model_availability()
            if not available:
                # Try to pull the model
                pulled = await llm.pull_model_if_needed()
                if not pulled:
                    pytest.skip("Ollama model not available and couldn't be pulled")
        
        # Test generation
        response = await llm._acall("What is 2+2? Answer briefly.")
        
        assert isinstance(response, str)
        assert len(response) > 0
        
        # Check metrics
        metrics = llm.get_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["successful_calls"] == 1
        assert metrics["error_count"] == 0
        assert metrics["average_latency"] > 0
    
    # @pytest.mark.skipif(
    #     not os.getenv("HUGGINGFACE_API_TOKEN"),
    #     reason="Hugging Face API token not available"
    # )
    # async def test_huggingface_end_to_end(self):
    #     """Test complete Hugging Face workflow"""
    #     llm = LLMFactory.create_llm(
    #         AgentType.PLANNING,
    #         ModelEnvironment.TESTING,
    #         max_tokens=50  # Keep response short for testing
    #     )
    #     
    #     response = await llm._acall("What is the capital of France?")
    #     
    #     assert isinstance(response, str)
    #     assert len(response) > 0
    #     assert "paris" in response.lower()
    #     
    #     # Check metrics
    #     metrics = llm.get_metrics()
    #     assert metrics["total_calls"] == 1
    #     assert metrics["successful_calls"] == 1
    #     assert metrics["error_count"] == 0

    # @pytest.mark.skipif(
    #     not os.getenv("HUGGINGFACE_API_TOKEN"),
    #     reason="Hugging Face API token not available"
    # )
    # async def test_huggingface_multiple_requests_stats(self):
    #     """Test that multiple requests properly update statistics"""
    #     llm = LLMFactory.create_llm(
    #         AgentType.CODE,
    #         ModelEnvironment.TESTING,
    #         max_tokens=20  # Keep responses short
    #     )
    #     
    #     # Make multiple requests
    #     await llm._acall("Count to 3")
    #     await llm._acall("What is 1+1?")
    #     await llm._acall("Say hello")
    #     
    #     # Check base metrics
    #     metrics = llm.get_metrics()
    #     assert metrics["total_calls"] == 3
    #     assert metrics["successful_calls"] == 3
    #     assert metrics["error_count"] == 0

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OpenAI API key not available"
    )
    async def test_openai_end_to_end(self):
        """Test complete OpenAI workflow"""
        llm = LLMFactory.create_llm(
            AgentType.PLANNING,
            ModelEnvironment.TESTING,
            max_tokens=50  # Keep response short for testing
        )
        
        response = await llm._acall("What is the capital of France?")
        
        assert isinstance(response, str)
        assert len(response) > 0
        assert "paris" in response.lower()
        
        # Check metrics
        metrics = llm.get_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["successful_calls"] == 1
        assert metrics["error_count"] == 0

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OpenAI API key not available"
    )
    async def test_openai_multiple_requests_stats(self):
        """Test that multiple requests properly update statistics"""
        llm = LLMFactory.create_llm(
            AgentType.CODE,
            ModelEnvironment.TESTING,
            max_tokens=20  # Keep responses short
        )
        
        # Make multiple requests
        await llm._acall("Count to 3")
        await llm._acall("What is 1+1?")
        await llm._acall("Say hello")
        
        # Check base metrics
        metrics = llm.get_metrics()
        assert metrics["total_calls"] == 3
        assert metrics["successful_calls"] == 3
        assert metrics["error_count"] == 0

    @pytest.mark.asyncio
    async def test_retry_logic_integration(self):
        """Test retry logic with simulated failures using test subclass"""

        
        class TestOllamaLLM(OllamaLLM):
            """Test subclass with controlled failure behavior"""
            call_count: int = 0
            
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                if self.call_count is None:
                    self.call_count = 0
            
            async def _make_api_call(
                self,
                prompt: str,
                stop: Optional[List[str]] = None,
                **kwargs: Any,
            ) -> str:
                """Override with predictable test behavior"""
                self.call_count += 1
                if self.call_count <= 2:
                    raise Exception(f"Simulated failure {self.call_count}")
                return "Success after retries"
        
        # Create test LLM instance
        llm = TestOllamaLLM(
            model_name="phi3:mini",
            max_retries=2,
            retry_delay=0.1,
            environment="development"
        )
        
        response = await llm._acall("Test prompt")
        
        assert response == "Success after retries"
        assert llm.call_count == 3  # Initial + 2 retries
        
        # Check metrics reflect the retries
        metrics = llm.get_metrics()
        assert metrics["total_calls"] == 3  # All attempts (2 failed + 1 success)
        assert metrics["successful_calls"] == 1  # Only successful calls
        assert metrics["error_count"] == 2  # Failed attempts
    
    @pytest.mark.asyncio
    async def test_caching_integration(self):
        """Test caching behavior in integration scenario using test subclass"""
        from src.core.llm_wrappers.ollama_llm import OllamaLLM
        from typing import Optional, List, Any
        
        class TestCachingOllamaLLM(OllamaLLM):
            """Test subclass with counting behavior"""
            call_count: int = 0
            
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                if self.call_count is None:
                    self.call_count = 0
            
            async def _make_api_call(
                self,
                prompt: str,
                stop: Optional[List[str]] = None,
                **kwargs: Any,
            ) -> str:
                """Override with counting behavior"""
                self.call_count += 1
                return f"Response {self.call_count}"
        
        # Create test LLM instance
        llm = TestCachingOllamaLLM(
            model_name="phi3:mini",
            enable_caching=True,
            environment="development"
        )
        
        # First call
        response1 = await llm._acall("Same prompt")
        # Second call (should hit cache)
        response2 = await llm._acall("Same prompt")
        # Third call with different prompt
        response3 = await llm._acall("Different prompt")
        
        assert response1 == response2  # Cache hit
        assert response1 != response3  # Different prompt
        assert llm.call_count == 2  # Only 2 actual API calls
        
        metrics = llm.get_metrics()
        assert metrics["cache_hits"] >= 1  # At least one cache hit
        assert metrics["cache_misses"] >= 2  # At least two cache misses
    
    
    # @pytest.mark.skipif(
    #     not os.getenv("HUGGINGFACE_API_TOKEN"),
    #     reason="Hugging Face API token not available"
    # )
    # async def test_huggingface_error_handling_integration(self):
    #     """Test error handling with invalid model name"""
    #     llm = LLMFactory.create_llm(
    #         AgentType.PLANNING,
    #         ModelEnvironment.TESTING
    #     )
    #     
    #     # Override model name to something invalid
    #     llm.model_name = "nonexistent/invalid-model"
    #     
    #     # This should fail with a clear error message
    #     with pytest.raises(Exception) as exc_info:
    #         await llm._acall("Test prompt")
    #     
    #     error_msg = str(exc_info.value)
    #     # Should contain helpful error information
    #     assert any(keyword in error_msg.lower() for keyword in [
    #         "not found", "invalid", "error", "failed"
    #     ])

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OpenAI API key not available"
    )
    async def test_openai_error_handling_integration(self):
        """Test error handling with invalid model name"""
        llm = LLMFactory.create_llm(
            AgentType.PLANNING,
            ModelEnvironment.TESTING
        )
        
        # Override model name to something invalid
        llm.model_name = "nonexistent-invalid-model"
        
        # This should fail with a clear error message
        with pytest.raises(Exception) as exc_info:
            await llm._acall("Test prompt")
        
        error_msg = str(exc_info.value)
        # Should contain helpful error information
        assert any(keyword in error_msg.lower() for keyword in [
            "not found", "invalid", "error", "failed", "model"
        ])