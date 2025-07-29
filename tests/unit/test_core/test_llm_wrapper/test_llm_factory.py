import pytest
import os
from unittest.mock import patch, AsyncMock
from src.core.llm_wrappers.llm_factory import LLMFactory, AgentType, ModelEnvironment
from src.core.llm_wrappers.ollama_llm import OllamaLLM
from src.core.llm_wrappers.huggingface_llm import HuggingFaceLLM
from src.core.llm_wrappers.vllm_llm import vLLMLLM

class TestLLMFactory:
    
    def test_create_development_llm(self):
        """Test creating LLM for development environment"""
        llm = LLMFactory.create_llm(
            AgentType.PLANNING,
            ModelEnvironment.DEVELOPMENT
        )
        
        assert isinstance(llm, OllamaLLM)
        assert llm.model_name == "phi3:mini"
        assert llm.environment == ModelEnvironment.DEVELOPMENT.value
    
    @patch.dict(os.environ, {'HUGGINGFACE_API_TOKEN': 'test-token'})
    def test_create_testing_llm(self):
        """Test creating LLM for testing environment"""
        llm = LLMFactory.create_llm(
            AgentType.RESEARCH,
            ModelEnvironment.TESTING
        )
        
        assert isinstance(llm, HuggingFaceLLM)
        assert llm.model_name == "mistralai/Mistral-7B-Instruct-v0.1"
        assert llm.environment == ModelEnvironment.TESTING.value
    
    def test_create_production_llm(self):
        """Test creating LLM for production environment"""
        llm = LLMFactory.create_llm(
            AgentType.CODE,
            ModelEnvironment.PRODUCTION
        )
        
        assert isinstance(llm, vLLMLLM)
        assert llm.model_name == "codellama/CodeLlama-7b-Instruct-hf"
        assert llm.environment == ModelEnvironment.PRODUCTION.value
    
    @patch.dict(os.environ, {'ENVIRONMENT': 'testing'})
    @patch.dict(os.environ, {'HUGGINGFACE_API_TOKEN': 'test-token'})
    def test_environment_detection_from_env_var(self):
        """Test automatic environment detection from environment variable"""
        llm = LLMFactory.create_llm(AgentType.PLANNING)
        
        assert isinstance(llm, HuggingFaceLLM)
        assert llm.environment == ModelEnvironment.TESTING.value
    
    def test_custom_parameters_override(self):
        """Test that custom parameters override defaults"""
        llm = LLMFactory.create_llm(
            AgentType.PLANNING,
            ModelEnvironment.DEVELOPMENT,
            max_retries=5,
            timeout=120.0,
            temperature=0.9
        )
        
        assert llm.max_retries == 5
        assert llm.timeout == 120.0
        assert llm.temperature == 0.9
    
    def test_get_available_models(self):
        """Test getting available models for environment"""
        models = LLMFactory.get_available_models(ModelEnvironment.DEVELOPMENT)
        
        assert AgentType.PLANNING in models
        assert AgentType.RESEARCH in models
        assert AgentType.CODE in models
        assert models[AgentType.PLANNING] == "phi3:mini"
    
    @pytest.mark.asyncio
    async def test_health_check_all_development(self):
        """Test health check for development environment"""
        with patch.object(OllamaLLM, 'check_model_availability', return_value=True):
            results = await LLMFactory.health_check_all(ModelEnvironment.DEVELOPMENT)
        
        assert AgentType.PLANNING.value in results
        assert AgentType.RESEARCH.value in results
        assert AgentType.CODE.value in results
        
        for agent_type in AgentType:
            result = results[agent_type.value]
            assert "available" in result
            assert result["type"] == "ollama"
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'HUGGINGFACE_API_TOKEN': 'test-token'})
    async def test_health_check_all_testing(self):
        """Test health check for testing environment"""
        mock_info = {"model_name": "test-model", "status": "available"}
        
        with patch.object(HuggingFaceLLM, 'get_model_info', return_value=mock_info):
            results = await LLMFactory.health_check_all(ModelEnvironment.TESTING)
        
        for agent_type in AgentType:
            result = results[agent_type.value]
            assert "info" in result
            assert result["type"] == "huggingface"
    
    @pytest.mark.asyncio
    async def test_health_check_with_errors(self):
        """Test health check when errors occur"""
        with patch.object(OllamaLLM, 'check_model_availability', side_effect=Exception("Connection failed")):
            results = await LLMFactory.health_check_all(ModelEnvironment.DEVELOPMENT)
        
        for agent_type in AgentType:
            result = results[agent_type.value]
            assert "error" in result
            assert "Connection failed" in result["error"]
