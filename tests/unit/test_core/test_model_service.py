# tests/unit/test_model_service.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.core.model_service import ModelService

class TestModelService:
    
    @pytest.fixture
    def model_service(self):
        with patch('src.core.model_service.EnvironmentAwareModelRouter') as mock_router_class:
            with patch('src.core.model_service.ModelFallbackChain') as mock_fallback_class:
                with patch('src.core.model_service.OllamaModelManager') as mock_ollama_class:
                    
                    # Setup mocks
                    mock_router = AsyncMock()
                    mock_fallback = Mock()
                    mock_ollama = Mock()
                    
                    mock_router_class.return_value = mock_router
                    mock_fallback_class.return_value = mock_fallback
                    mock_ollama_class.return_value = mock_ollama
                    
                    # Configure router environment
                    mock_router.env_config.environment.value = "development"
                    
                    service = ModelService()
                    service.router = mock_router
                    service.fallback_chain = mock_fallback
                    service.ollama_manager = mock_ollama
                    
                    return service
    
    @pytest.mark.asyncio
    async def test_generate_response_success(self, model_service):
        """Test successful response generation"""
        expected_response = {
            "response": "Test response",
            "model_used": "phi3:mini",
            "fallback_used": False,
            "execution_time": 1.5
        }
        
        model_service.fallback_chain.execute_with_fallback = AsyncMock(return_value=expected_response)
        
        result = await model_service.generate_response("Test prompt", "planning")
        
        assert result == expected_response
        model_service.fallback_chain.execute_with_fallback.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_response_with_context(self, model_service):
        """Test response generation with context"""
        context = {"requires_reasoning": True}
        expected_response = {
            "response": "Complex response",
            "model_used": "phi3:mini",
            "fallback_used": False
        }
        
        model_service.fallback_chain.execute_with_fallback = AsyncMock(return_value=expected_response)
        
        result = await model_service.generate_response("Complex task", "research", context)
        
        assert result == expected_response
        # Verify context was passed through
        call_args = model_service.fallback_chain.execute_with_fallback.call_args
        assert call_args[0][3] == context  # Fourth argument should be context
    
    @pytest.mark.asyncio
    async def test_generate_response_development_environment(self, model_service):
        """Test response generation in development environment uses Ollama"""
        model_service.router.env_config.environment.value = "development"
        model_service.ollama_manager.generate_response = AsyncMock(return_value="Ollama response")
        
        # Mock the fallback chain to call our model executor
        async def mock_execute_with_fallback(task, agent_type, model_executor, context=None):
            response = await model_executor("phi3:mini", task)
            return {
                "response": response,
                "model_used": "phi3:mini",
                "fallback_used": False
            }
        
        model_service.fallback_chain.execute_with_fallback = mock_execute_with_fallback
        
        result = await model_service.generate_response("Test prompt")
        
        assert result["response"] == "Ollama response"
        model_service.ollama_manager.generate_response.assert_called_once_with("Test prompt", "phi3:mini")
    
    @pytest.mark.asyncio
    async def test_generate_response_cloud_environment(self, model_service):
        """Test response generation in cloud environment"""
        model_service.router.env_config.environment.value = "testing"
        
        # Mock cloud model execution
        model_service._execute_cloud_model = AsyncMock(return_value="Cloud response")
        
        # Mock the fallback chain to call our model executor
        async def mock_execute_with_fallback(task, agent_type, model_executor, context=None):
            response = await model_executor("cloud-model", task)
            return {
                "response": response,
                "model_used": "cloud-model",
                "fallback_used": False
            }
        
        model_service.fallback_chain.execute_with_fallback = mock_execute_with_fallback
        
        result = await model_service.generate_response("Test prompt")
        
        assert result["response"] == "Cloud response"
        model_service._execute_cloud_model.assert_called_once_with("cloud-model", "Test prompt")
    
    @pytest.mark.asyncio
    async def test_get_system_status(self, model_service):
        """Test system status reporting"""
        # Mock router status
        model_service.router.env_config.environment.value = "development"
        model_service.router.model_metrics = {"phi3:mini": Mock()}
        
        # Mock fallback status
        model_service.fallback_chain.get_fallback_status = Mock(return_value={
            "circuit_breakers": {},
            "model_health": {}
        })
        
        # Mock resource status
        model_service.router.resource_monitor.get_current_metrics = AsyncMock(return_value={
            "cpu_usage": 50.0,
            "memory_usage": 60.0
        })
        
        status = await model_service.get_system_status()
        
        assert "router_status" in status
        assert "fallback_status" in status
        assert "resource_status" in status
        assert status["router_status"]["environment"] == "development"
    
    @pytest.mark.asyncio
    async def test_execute_cloud_model_placeholder(self, model_service):
        """Test cloud model execution placeholder"""
        result = await model_service._execute_cloud_model("test-model", "test prompt")
        
        assert "Response from test-model" in result
        assert "test prompt" in result

if __name__ == "__main__":
    pytest.main([__file__])
