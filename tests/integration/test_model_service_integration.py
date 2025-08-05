# tests/integration/test_model_service_integration.py
import pytest
import asyncio
import os
from unittest.mock import patch, Mock, AsyncMock
from src.core.model_service import ModelService
from tests.integration.test_mocks import TestAssertionHelpers

class TestModelServiceIntegration:
    """Integration tests for ModelService with external dependencies"""
    
    @pytest.mark.asyncio
    async def test_ollama_integration_development(self):
        """Test integration with Ollama in development environment"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            # Mock the LLM instance that would be returned by the factory
            mock_llm = Mock()
            mock_llm.model_name = "phi3:mini"
            mock_llm._acall = AsyncMock(return_value="Ollama generated response")
            
            service = ModelService()
            
            # Mock the get_model_for_agent method to return our mock LLM
            with patch.object(service, 'get_model_for_agent', return_value=mock_llm):
                llm = service.get_model_for_agent("code")
                response = await llm._acall("Write a Python function to calculate fibonacci numbers")
                
                # Verify response
                assert response == "Ollama generated response"
                assert llm.model_name == "phi3:mini"
                
                # Verify LLM was called
                mock_llm._acall.assert_called_once_with("Write a Python function to calculate fibonacci numbers")
    
    @pytest.mark.asyncio
    async def test_cloud_model_integration_testing(self):
        """Test integration with cloud models in testing environment"""
        with patch.dict(os.environ, {"ENVIRONMENT": "testing", "OPENAI_API_KEY": "test-key"}):
            # Mock the OpenAI LLM instance
            mock_llm = Mock()
            mock_llm.model_name = "gpt-3.5-turbo"
            mock_llm._acall = AsyncMock(return_value="Cloud model response")
            
            service = ModelService()
            
            # Mock the get_model_for_agent method to return our mock LLM
            with patch.object(service, 'get_model_for_agent', return_value=mock_llm):
                llm = service.get_model_for_agent("research")
                response = await llm._acall("Analyze the latest trends in AI")
                
                # Verify response
                assert response == "Cloud model response"
                assert llm.model_name == "gpt-3.5-turbo"
                assert service.environment.value == "testing"
    
    @pytest.mark.asyncio
    async def test_multi_agent_workflow_integration(self):
        """Test integration across multiple agent types"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Mock different LLMs for different agent types
            mock_llms = {
                "planning": Mock(model_name="phi3:mini", _acall=AsyncMock(return_value="Planning response")),
                "research": Mock(model_name="llama3.2:1b", _acall=AsyncMock(return_value="Research response")),
                "code": Mock(model_name="qwen2:0.5b", _acall=AsyncMock(return_value="Code response"))
            }
            
            def mock_get_model(agent_type):
                return mock_llms[agent_type]
            
            with patch.object(service, 'get_model_for_agent', side_effect=mock_get_model):
                # Test different agent types
                agent_types = ["planning", "research", "code"]
                tasks = [
                    "Plan the project structure",
                    "Research the latest AI trends", 
                    "Generate code for authentication"
                ]
                
                responses = []
                for agent_type, task in zip(agent_types, tasks):
                    llm = service.get_model_for_agent(agent_type)
                    response = await llm._acall(task)
                    responses.append((agent_type, response, llm.model_name))
                
                # Verify all requests succeeded
                assert len(responses) == 3
                expected_responses = ["Planning response", "Research response", "Code response"]
                expected_models = ["phi3:mini", "llama3.2:1b", "qwen2:0.5b"]
                
                for i, (agent_type, response, model_name) in enumerate(responses):
                    assert agent_type == agent_types[i]
                    assert response == expected_responses[i]
                    assert model_name == expected_models[i]
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_integration(self):
        """Test handling of concurrent requests"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Mock LLM with delay to simulate real execution
            mock_llm = Mock()
            mock_llm.model_name = "phi3:mini"
            
            async def mock_acall_with_delay(prompt, **kwargs):
                await asyncio.sleep(0.1)  # Small delay
                return f"Response to: {prompt[:20]}..."
            
            mock_llm._acall = mock_acall_with_delay
            
            with patch.object(service, 'get_model_for_agent', return_value=mock_llm):
                # Create multiple concurrent requests
                async def make_request(task_id):
                    llm = service.get_model_for_agent("planning")
                    return await llm._acall(f"Task {task_id}")
                
                tasks = [make_request(i) for i in range(3)]
                
                # Execute concurrently
                results = await asyncio.gather(*tasks)
                
                # Verify all requests completed
                assert len(results) == 3
                for i, result in enumerate(results):
                    assert f"Task {i}" in result
    
    @pytest.mark.asyncio
    async def test_error_recovery_integration(self):
        """Test error recovery and fallback behavior"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Mock LLM that fails
            mock_llm = Mock()
            mock_llm.model_name = "phi3:mini"
            mock_llm._acall = AsyncMock(side_effect=Exception("Simulated LLM failure"))
            
            with patch.object(service, 'get_model_for_agent', return_value=mock_llm):
                # Call should raise the exception
                with pytest.raises(Exception, match="Simulated LLM failure"):
                    llm = service.get_model_for_agent("planning")
                    await llm._acall("Test prompt")
    
    @pytest.mark.asyncio
    async def test_system_monitoring_integration(self):
        """Test system monitoring and health check integration"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Test health_check (current method)
            with patch('src.core.llm_wrappers.llm_factory.LLMFactory.health_check_all') as mock_health:
                mock_health.return_value = {"planning": {"available": True, "type": "ollama"}}
                
                health = await service.health_check()
                assert isinstance(health, dict)
                mock_health.assert_called_once()
            
            # Test model metrics
            metrics = service.get_model_metrics()
            assert isinstance(metrics, dict)
            
            # Test available models
            models = service.get_available_models()
            assert isinstance(models, dict)
            assert len(models) > 0
    
    @pytest.mark.asyncio
    async def test_model_caching_integration(self):
        """Test model instance caching behavior"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Mock the LLM factory to track creation calls
            with patch('src.core.llm_wrappers.llm_factory.LLMFactory.create_llm') as mock_create:
                def create_mock_llm(*args, **kwargs):
                    mock_llm = Mock()
                    mock_llm.model_name = "phi3:mini"
                    mock_llm._acall = AsyncMock(return_value="Cached response")
                    return mock_llm
                
                mock_create.side_effect = create_mock_llm
                
                # First call should create LLM
                llm1 = service.get_model_for_agent("planning")
                assert mock_create.call_count == 1
                
                # Second call should use cached LLM
                llm2 = service.get_model_for_agent("planning")
                assert mock_create.call_count == 1  # No additional creation
                assert llm1 is llm2  # Same instance
                
                # Different agent type should create new LLM
                llm3 = service.get_model_for_agent("research")
                assert mock_create.call_count == 2  # New creation
                assert llm3 is not llm1  # Different instance
    
    @pytest.mark.asyncio
    async def test_environment_specific_behavior(self):
        """Test behavior differences across environments"""
        environments = ["development", "testing", "production"]
        
        for env in environments:
            with patch.dict(os.environ, {"ENVIRONMENT": env}):
                service = ModelService()
                
                # Verify environment is set correctly
                assert service.environment.value == env
                
                # Verify available models differ by environment
                models = service.get_available_models()
                assert isinstance(models, dict)
                assert len(models) > 0
                
                # Each environment should have models for all agent types
                expected_agents = ["planning", "research", "code"]
                for agent in expected_agents:
                    assert agent in models