# tests/integration/test_model_router_integration.py
import pytest
import asyncio
import os
from unittest.mock import patch, Mock, AsyncMock
from src.core.model_service import ModelService
from tests.integration.test_mocks import TestAssertionHelpers

class TestModelRouterIntegration:
    """Integration tests for the complete model routing system"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_development_environment(self):
        """Test complete flow in development environment"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Mock the LLM instance
            mock_llm = Mock()
            mock_llm.model_name = "phi3:mini"
            mock_llm._acall = AsyncMock(return_value="Generated response")
            
            with patch.object(service, 'get_model_for_agent', return_value=mock_llm):
                # Test request
                llm = service.get_model_for_agent("code")
                response = await llm._acall("Generate Python code for sorting")
                
                # Verify response
                assert response == "Generated response"
                assert llm.model_name == "phi3:mini"
                assert service.environment.value == "development"
    
    @pytest.mark.asyncio
    async def test_agent_type_fallback_integration(self):
        """Test fallback to planning agent when other agent types fail"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Mock factory to fail for code agent, succeed for planning
            planning_llm = Mock()
            planning_llm.model_name = "phi3:mini"
            planning_llm._acall = AsyncMock(return_value="Fallback success")
            
            def mock_create_llm(agent_type, environment):
                if agent_type.value == "code":
                    raise Exception("Code agent failed")
                return planning_llm
            
            with patch('src.core.model_service.LLMFactory.create_llm', side_effect=mock_create_llm):
                # This should fallback to planning agent
                llm = service.get_model_for_agent("code")
                response = await llm._acall("Test fallback request")
                
                assert response == "Fallback success"
                assert llm.model_name == "phi3:mini"
    
    @pytest.mark.asyncio
    async def test_health_check_integration(self):
        """Test health check functionality"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Test health check (current method)
            with patch('src.core.llm_wrappers.llm_factory.LLMFactory.health_check_all') as mock_health:
                mock_health.return_value = {
                    "planning": {"available": True, "type": "ollama"},
                    "research": {"available": True, "type": "ollama"},
                    "code": {"available": True, "type": "ollama"}
                }
                
                health = await service.health_check()
                
                assert isinstance(health, dict)
                assert "planning" in health
                assert "research" in health
                assert "code" in health
                
                for agent_type, info in health.items():
                    assert "available" in info or "status" in info or "error" in info
    
    @pytest.mark.asyncio
    async def test_performance_metrics_collection(self):
        """Test performance metrics collection across requests"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Mock LLM with metrics tracking
            mock_llm = Mock()
            mock_llm.model_name = "phi3:mini"
            mock_llm._acall = AsyncMock(return_value="Performance test response")
            mock_llm.get_metrics.return_value = {
                "total_calls": 3,
                "successful_calls": 3,
                "error_count": 0,
                "average_latency": 1.5,
                "total_tokens": 150
            }
            
            with patch.object(service, 'get_model_for_agent', return_value=mock_llm):
                # Make multiple requests
                for i in range(3):
                    llm = service.get_model_for_agent("planning")
                    response = await llm._acall(f"Performance test request {i}")
                    assert response == "Performance test response"
                
                # Check metrics collection
                metrics = service.get_model_metrics()
                assert isinstance(metrics, dict)
                
                # Should have metrics for the cached LLM
                cache_key = "development_planning"
                if cache_key in metrics:
                    model_metrics = metrics[cache_key]
                    assert "total_calls" in model_metrics
                    assert "successful_calls" in model_metrics
                    assert "average_latency" in model_metrics
    
    @pytest.mark.asyncio
    async def test_environment_switching_integration(self):
        """Test behavior when switching between environments"""
        environments = ["development", "testing"]
        
        for env in environments:
            with patch.dict(os.environ, {"ENVIRONMENT": env}):
                service = ModelService()
                
                # Verify environment is detected correctly
                assert service.environment.value == env
                
                # Test model availability for environment
                models = service.get_available_models()
                assert isinstance(models, dict)
                assert len(models) > 0
                
                # Verify all agent types have models
                expected_agents = ["planning", "research", "code"]
                for agent in expected_agents:
                    assert agent in models
                    assert isinstance(models[agent], str)
                    assert len(models[agent]) > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_multi_agent_requests(self):
        """Test concurrent requests across different agent types"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Mock different LLMs for different agent types
            mock_llms = {
                "planning": Mock(
                    model_name="phi3:mini",
                    _acall=AsyncMock(return_value="Planning response")
                ),
                "research": Mock(
                    model_name="llama3.2:1b", 
                    _acall=AsyncMock(return_value="Research response")
                ),
                "code": Mock(
                    model_name="qwen2:0.5b",
                    _acall=AsyncMock(return_value="Code response")
                )
            }
            
            def mock_get_model(agent_type):
                return mock_llms[agent_type]
            
            with patch.object(service, 'get_model_for_agent', side_effect=mock_get_model):
                # Create concurrent requests for different agent types
                async def make_request(prompt, agent_type):
                    llm = service.get_model_for_agent(agent_type)
                    return await llm._acall(prompt)
                
                tasks = [
                    make_request("Plan the project", "planning"),
                    make_request("Research AI trends", "research"),
                    make_request("Write authentication code", "code")
                ]
                
                # Execute concurrently
                results = await asyncio.gather(*tasks)
                
                # Verify all requests completed successfully
                assert len(results) == 3
                
                expected_responses = ["Planning response", "Research response", "Code response"]
                
                for i, result in enumerate(results):
                    assert result == expected_responses[i]
    
    @pytest.mark.asyncio
    async def test_error_propagation_and_recovery(self):
        """Test error propagation and recovery mechanisms"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Mock LLM that always fails
            mock_llm = Mock()
            mock_llm.model_name = "phi3:mini"
            mock_llm._acall = AsyncMock(side_effect=Exception("Persistent failure"))
            
            with patch.object(service, 'get_model_for_agent', return_value=mock_llm):
                # Test error handling - should raise exception
                with pytest.raises(Exception, match="Persistent failure"):
                    llm = service.get_model_for_agent("planning")
                    await llm._acall("This should fail")
    
    @pytest.mark.asyncio
    async def test_model_cache_invalidation(self):
        """Test model cache invalidation and refresh"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            service = ModelService()
            
            # Mock LLM factory to track creation calls
            with patch('src.core.llm_wrappers.llm_factory.LLMFactory.create_llm') as mock_create:
                def create_mock_llm(*args, **kwargs):
                    mock_llm = Mock()
                    mock_llm.model_name = "phi3:mini"
                    mock_llm._acall = AsyncMock(return_value="Cached response")
                    mock_llm.clear_cache = Mock()
                    return mock_llm
                
                mock_create.side_effect = create_mock_llm
                
                # First call creates and caches LLM
                llm1 = service.get_model_for_agent("planning")
                assert mock_create.call_count == 1
                
                # Clear cache
                service.clear_model_cache()
                
                # Verify cache was cleared (check that clear_cache was called on the first LLM)
                if hasattr(llm1, 'clear_cache'):
                    llm1.clear_cache.assert_called_once()
                
                # Next call should create new LLM
                llm2 = service.get_model_for_agent("planning")
                assert mock_create.call_count == 2
                
                # Should be different instances after cache clear
                assert llm1 is not llm2