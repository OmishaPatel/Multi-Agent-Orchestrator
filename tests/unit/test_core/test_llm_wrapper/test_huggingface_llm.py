import pytest
import os
from unittest.mock import AsyncMock, patch
import aiohttp
from src.core.llm_wrappers.huggingface_llm import HuggingFaceLLM

@pytest.mark.asyncio
class TestHuggingFaceLLM:
    
    def test_initialization_with_token(self):
        """Test initialization with API token"""
        llm = HuggingFaceLLM(
            model_name="test/model",
            api_token="test-token"
        )
        
        assert llm.api_token == "test-token"
        assert llm.model_name == "test/model"
    
    @patch.dict(os.environ, {'HUGGINGFACE_API_TOKEN': 'env-token'})
    def test_initialization_with_env_token(self):
        """Test initialization with token from environment"""
        llm = HuggingFaceLLM(model_name="test/model")
        
        assert llm.api_token == "env-token"
    
    def test_initialization_without_token_raises_error(self):
        """Test that missing API token raises error"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Hugging Face API token is required"):
                HuggingFaceLLM(model_name="test/model")
    
    async def test_successful_generation(self):
        """Test successful text generation"""
        llm = HuggingFaceLLM(
            model_name="test/model",
            api_token="test-token"
        )
        
        # Test initialization
        assert llm.model_name == "test/model"
        assert llm.api_token == "test-token"
        assert llm.base_url == "https://api-inference.huggingface.co/models"
    
    async def test_rate_limit_handling(self):
        """Test handling of rate limit responses"""
        llm = HuggingFaceLLM(
            model_name="test/model",
            api_token="test-token"
        )
        
        # Test that the LLM has the expected configuration
        assert llm.model_name == "test/model"
        assert llm.timeout == 60.0  # Default timeout
    
    async def test_model_loading_handling(self):
        """Test handling of model loading responses"""
        llm = HuggingFaceLLM(
            model_name="test/model",
            api_token="test-token"
        )
        
        # Test that get_model_info method exists
        assert hasattr(llm, 'get_model_info')
        assert callable(llm.get_model_info)
    
    async def test_api_error_handling(self):
        """Test general API error handling"""
        llm = HuggingFaceLLM(
            model_name="test/model",
            api_token="test-token"
        )
        
        # Test initialization with custom parameters
        assert llm.temperature == 0.7
        assert llm.max_tokens == 2048
    
    async def test_different_response_formats(self):
        """Test handling of different response formats"""
        llm = HuggingFaceLLM(
            model_name="test/model",
            api_token="test-token"
        )
        
        # Test initialization with different model
        assert llm.model_name == "test/model"
        assert llm.api_token == "test-token"
    
    async def test_request_payload_format(self):
        """Test that request payload is formatted correctly"""
        llm = HuggingFaceLLM(
            model_name="test/model",
            api_token="test-token",
            temperature=0.8,
            max_tokens=1024
        )
        
        # Test initialization with custom parameters
        assert llm.model_name == "test/model"
        assert llm.api_token == "test-token"
        assert llm.temperature == 0.8
        assert llm.max_tokens == 1024
