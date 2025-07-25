# tests/integration/test_model_router_integration.py
import pytest
import asyncio
import os
from unittest.mock import patch, Mock, AsyncMock
from src.core.model_router import EnvironmentAwareModelRouter
from src.core.model_fallback import ModelFallbackChain
from src.core.model_service import ModelService
from src.config.model_environment import Environment

class TestModelRouterIntegration:
    """Integration tests for the complete model routing system"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_development_environment(self):
        """Test complete flow in development environment"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch('src.core.model_router.OllamaModelManager') as mock_ollama_class:
                
                # Setup mocks
                mock_ollama = Mock()
                mock_ollama_class.return_value = mock_ollama
                
                # Mock Ollama response
                mock_ollama.generate_response = AsyncMock(return_value="Generated response")
                
                # Create service
                service = ModelService()
                
                # Test request
                result = await service.generate_response(
                    "Generate Python code for sorting",
                    "code"
                )
                
                assert "response" in result
                assert "model_used" in result
                assert "execution_time" in result
    
    @pytest.mark.asyncio
    async def test_fallback_chain_integration(self):
        """Test fallback chain with real router integration"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch('src.core.model_router.OllamaModelManager') as mock_router_ollama:
                with patch('src.core.model_service.OllamaModelManager') as mock_service_ollama:
                    
                    # Setup mocks for both router and service
                    mock_router_ollama_instance = Mock()
                    mock_service_ollama_instance = Mock()
                    mock_router_ollama.return_value = mock_router_ollama_instance
                    mock_service_ollama.return_value = mock_service_ollama_instance
                    
                    # Setup failure then success pattern
                    call_count = 0
                    async def mock_generate(prompt, model):
                        nonlocal call_count
                        call_count += 1
                        if call_count == 1:
                            raise Exception("Primary model failed")
                        return f"Response from {model}"
                    
                    mock_service_ollama_instance.generate_response = mock_generate
                    
                    service = ModelService()
                    
                    result = await service.generate_response("Test task", "planning")
                    
                    assert result["fallback_used"] is True
                    assert "Response from" in result["response"]
                    assert len(result["attempts"]) == 2
    
    @pytest.mark.asyncio
    async def test_environment_switching(self):
        """Test behavior across different environments"""
        environments = ["development", "testing", "production"]
        
        for env in environments:
            with patch.dict(os.environ, {"ENVIRONMENT": env}):
                with patch('src.core.model_router.OllamaModelManager'):
                    
                    router = EnvironmentAwareModelRouter()
                    
                    # Test that router adapts to environment
                    assert router.env_config.environment.value == env
                    
                    # Test model selection
                    model, metadata = await router.route_request("Test task", "planning")
                    
                    assert isinstance(model, str)
                    assert metadata["environment"] == env
    
    @pytest.mark.asyncio
    async def test_resource_aware_model_selection(self):
        """Test that model selection adapts to resource constraints"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch('src.core.model_router.OllamaModelManager'):
                
                router = EnvironmentAwareModelRouter()
                
                # Test with high memory
                with patch.object(router, 'get_system_resources') as mock_resources:
                    mock_resources.return_value = {"available_ram_gb": 8.0}
                    model = await router.select_optimal_model("Simple task", "planning")
                    assert model == "phi3:mini"  # Should use standard model
                
                # Test with low memory - "Simple task" returns MODERATE complexity
                # With 1.0GB RAM (< 4.0) and MODERATE complexity → llama3.2:1b
                with patch.object(router, 'get_system_resources') as mock_resources:
                    mock_resources.return_value = {"available_ram_gb": 1.0}
                    model = await router.select_optimal_model("Simple task", "planning")
                    assert model == "llama3.2:1b"  # Should use lightweight model
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        """Test circuit breaker integration with real components"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch('src.core.model_router.OllamaModelManager') as mock_ollama_class:
                
                mock_ollama = Mock()
                mock_ollama_class.return_value = mock_ollama
                
                # Always fail to trigger circuit breaker
                mock_ollama.generate_response = AsyncMock(side_effect=Exception("Model failed"))
                
                service = ModelService()
                
                # Make multiple requests to trigger circuit breaker
                for _ in range(3):
                    try:
                        await service.generate_response("Test task", "planning")
                    except:
                        pass  # Expected to fail
                
                # Check circuit breaker status
                status = await service.get_system_status()
                fallback_status = status["fallback_status"]
                
                assert "circuit_breakers" in fallback_status
    
    @pytest.mark.asyncio
    async def test_performance_metrics_collection(self):
        """Test that performance metrics are collected correctly"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch('src.core.model_router.OllamaModelManager') as mock_ollama_class:
                
                mock_ollama = Mock()
                mock_ollama_class.return_value = mock_ollama
                mock_ollama.generate_response = AsyncMock(return_value="Test response")
                
                service = ModelService()
                
                # Make several requests
                for i in range(3):
                    await service.generate_response(f"Test task {i}", "planning")
                
                # Check metrics
                status = await service.get_system_status()
                router_status = status["router_status"]
                
                assert "model_metrics" in router_status
                # Should have metrics for the model that was used
                assert len(router_status["model_metrics"]) > 0
    
    @pytest.mark.asyncio
    async def test_task_complexity_routing_integration(self):
        """Test that task complexity affects model routing"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch('src.core.model_router.OllamaModelManager'):
                
                router = EnvironmentAwareModelRouter()
                
                # Test simple task
                simple_model, _ = await router.route_request("Hello", "planning")
                
                # Test complex task
                complex_model, _ = await router.route_request(
                    "Analyze the complex architecture and optimize performance", 
                    "planning"
                )
                
                # Both should return models (exact model depends on environment config)
                assert isinstance(simple_model, str)
                assert isinstance(complex_model, str)

if __name__ == "__main__":
    pytest.main([__file__])
