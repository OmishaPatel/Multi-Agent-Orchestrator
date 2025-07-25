# tests/integration/test_model_service_integration.py
import pytest
import asyncio
import os
from unittest.mock import patch, Mock, AsyncMock
from src.core.model_service import ModelService

class TestModelServiceIntegration:
    """Integration tests for ModelService with external dependencies"""
    
    @pytest.mark.asyncio
    async def test_ollama_integration_development(self):
        """Test integration with Ollama in development environment"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch('src.core.model_service.OllamaModelManager') as mock_ollama_class:
                
                # Create a more realistic Ollama mock
                mock_ollama = Mock()
                mock_ollama_class.return_value = mock_ollama
                
                # Mock successful Ollama response
                mock_ollama.generate_response = AsyncMock(return_value="Ollama generated response")
                
                service = ModelService()
                
                result = await service.generate_response(
                    "Write a Python function to calculate fibonacci numbers",
                    "code"
                )
                
                assert "response" in result
                assert result["response"] == "Ollama generated response"
                assert "model_used" in result
                assert "execution_time" in result
                
                # Verify Ollama was called
                mock_ollama.generate_response.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cloud_model_integration_testing(self):
        """Test integration with cloud models in testing environment"""
        with patch.dict(os.environ, {"ENVIRONMENT": "testing"}):
            service = ModelService()
            
            # Mock cloud model execution
            with patch.object(service, '_execute_cloud_model') as mock_cloud:
                mock_cloud.return_value = "Cloud model response"
                
                # Mock the fallback chain to use cloud executor
                async def mock_execute_with_fallback(task, agent_type, model_executor, context=None):
                    response = await model_executor("cloud-model", task)
                    return {
                        "response": response,
                        "model_used": "cloud-model",
                        "fallback_used": False,
                        "execution_time": 2.0
                    }
                
                service.fallback_chain.execute_with_fallback = mock_execute_with_fallback
                
                result = await service.generate_response(
                    "Analyze market trends",
                    "research"
                )
                
                assert result["response"] == "Cloud model response"
                assert result["model_used"] == "cloud-model"
                mock_cloud.assert_called_once_with("cloud-model", "Analyze market trends")
    
    @pytest.mark.asyncio
    async def test_multi_agent_workflow_integration(self):
        """Test integration across multiple agent types"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch('src.core.model_service.OllamaModelManager') as mock_ollama_class:
                
                mock_ollama = Mock()
                mock_ollama_class.return_value = mock_ollama
                
                # Different responses for different agent types
                async def mock_generate(prompt, model):
                    if "code" in prompt.lower():
                        return f"Code response from {model}"
                    elif "research" in prompt.lower():
                        return f"Research response from {model}"
                    else:
                        return f"Planning response from {model}"
                
                mock_ollama.generate_response = mock_generate
                
                service = ModelService()
                
                # Test different agent types
                agent_types = ["planning", "research", "code"]
                tasks = [
                    "Plan the project structure",
                    "Research the latest AI trends", 
                    "Generate code for authentication"
                ]
                
                results = []
                for agent_type, task in zip(agent_types, tasks):
                    result = await service.generate_response(task, agent_type)
                    results.append(result)
                
                # Verify all requests succeeded
                assert len(results) == 3
                for result in results:
                    assert "response" in result
                    assert "model_used" in result
                    assert result["fallback_used"] is False
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_integration(self):
        """Test handling of concurrent requests"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch('src.core.model_service.OllamaModelManager') as mock_ollama_class:
                
                mock_ollama = Mock()
                mock_ollama_class.return_value = mock_ollama
                
                # Add delay to simulate real model execution
                async def mock_generate_with_delay(prompt, model):
                    await asyncio.sleep(0.1)  # Small delay
                    return f"Response to: {prompt[:20]}..."
                
                mock_ollama.generate_response = mock_generate_with_delay
                
                service = ModelService()
                
                # Create multiple concurrent requests
                tasks = [
                    service.generate_response(f"Task {i}", "planning")
                    for i in range(5)
                ]
                
                # Execute concurrently
                results = await asyncio.gather(*tasks)
                
                # Verify all requests completed successfully
                assert len(results) == 5
                for i, result in enumerate(results):
                    assert "response" in result
                    assert f"Task {i}" in result["response"]
    
    @pytest.mark.asyncio
    async def test_error_recovery_integration(self):
        """Test error recovery across the integrated system"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            with patch('src.core.model_service.OllamaModelManager') as mock_ollama_class:
                
                mock_ollama = Mock()
                mock_ollama_class.return_value = mock_ollama
                
                # Simulate intermittent failures
                call_count = 0
                async def mock_generate_with_failures(prompt, model):
                    nonlocal call_count
                    call_count += 1
                    
                    # Fail on first few calls, then succeed
                    if call_count <= 2:
                        raise Exception(f"Simulated failure {call_count}")
                    return f"Success response from {model}"
                
                mock_ollama.generate_response = mock_generate_with_failures
                
                service = ModelService()
                
                # This should eventually succeed due to fallback
                result = await service.generate_response("Test task", "planning")
                
                assert "response" in result
                assert "Success response" in result["response"]
                assert result["fallback_used"] is True
                assert len(result["attempts"]) > 1
    
    @pytest.mark.asyncio
    async def test_system_monitoring_integration(self):
        """Test system monitoring and status reporting integration"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Make some requests to generate metrics
            with patch.object(service.ollama_manager, 'generate_response') as mock_generate:
                mock_generate.return_value = "Test response"
                
                # Mock the fallback execution to simulate real usage
                async def mock_execute_with_fallback(task, agent_type, model_executor, context=None):
                    response = await model_executor("phi3:mini", task)
                    return {
                        "response": response,
                        "model_used": "phi3:mini",
                        "fallback_used": False,
                        "execution_time": 1.5
                    }
                
                service.fallback_chain.execute_with_fallback = mock_execute_with_fallback
                
                # Make several requests
                for i in range(3):
                    await service.generate_response(f"Test task {i}", "planning")
                
                # Get system status
                status = await service.get_system_status()
                
                # Verify status structure
                assert "router_status" in status
                assert "fallback_status" in status
                assert "resource_status" in status
                
                # Verify router status
                router_status = status["router_status"]
                assert "environment" in router_status
                assert router_status["environment"] == "development"

if __name__ == "__main__":
    pytest.main([__file__])
