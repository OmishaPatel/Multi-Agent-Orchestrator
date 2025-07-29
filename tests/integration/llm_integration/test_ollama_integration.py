# tests/integration/llm_integration/test_ollama_integration.py
"""
Basic integration tests for Ollama LLM wrapper.
These tests verify the Ollama LLM wrapper works with actual Ollama server.
"""

import pytest
import os
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.core.llm_wrappers.ollama_llm import OllamaLLM

@pytest.mark.integration
class TestOllamaIntegration:
    """Basic integration tests for Ollama LLM wrapper"""
    
    @pytest.mark.skipif(
        not os.getenv("TEST_OLLAMA", "").lower() == "true",
        reason="Ollama integration tests disabled"
    )
    @pytest.mark.asyncio
    async def test_ollama_basic_generation(self):
        """Test basic text generation with Ollama"""
        llm = OllamaLLM(model_name="phi3:mini")
        
        # Check if model is available
        available = await llm.check_model_availability()
        if not available:
            pytest.skip("Ollama model phi3:mini not available")
        
        # Test generation
        response = await llm._acall("What is 2+2? Answer with just the number.")
        
        assert isinstance(response, str)
        assert len(response) > 0
        assert "4" in response
        
        # Check metrics
        metrics = llm.get_metrics()
        assert metrics["total_calls"] >= 1
        assert metrics["error_count"] == 0
    
    @pytest.mark.skipif(
        not os.getenv("TEST_OLLAMA", "").lower() == "true",
        reason="Ollama integration tests disabled"
    )
    @pytest.mark.asyncio
    async def test_ollama_model_availability(self):
        """Test model availability checking"""
        llm = OllamaLLM(model_name="phi3:mini")
        
        available = await llm.check_model_availability()
        assert isinstance(available, bool)
        
        if available:
            # If model is available, test generation should work
            response = await llm._acall("Hello")
            assert isinstance(response, str)
            assert len(response) > 0
    
    @pytest.mark.skipif(
        not os.getenv("TEST_OLLAMA", "").lower() == "true",
        reason="Ollama integration tests disabled"
    )
    @pytest.mark.asyncio
    async def test_ollama_error_handling(self):
        """Test error handling with non-existent model"""
        llm = OllamaLLM(model_name="nonexistent:model")
        
        # This should fail gracefully
        with pytest.raises(Exception):
            await llm._acall("Test prompt")
        
        # Error should be recorded in metrics
        metrics = llm.get_metrics()
        assert metrics["error_count"] > 0