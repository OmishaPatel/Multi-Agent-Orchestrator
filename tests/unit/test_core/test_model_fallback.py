# tests/unit/test_model_fallback.py
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import time
from src.core.model_fallback import ModelFallbackChain, FallbackAttempt
from src.config.model_environment import Environment

class TestModelFallbackChain:
    
    @pytest.fixture
    def router_mock(self):
        router = Mock()
        router.env_config.environment = Environment.DEVELOPMENT
        router.fallback_configs = {
            Environment.DEVELOPMENT: Mock(
                primary_model="phi3:mini",
                fallback_models=["llama3.2:1b", "qwen2:0.5b"],
                max_retries=2,
                retry_delay=0.01  # Very short delay for tests
            )
        }
        router._update_model_metrics = Mock()
        return router
    
    @pytest.fixture
    def fallback_chain(self, router_mock):
        return ModelFallbackChain(router_mock)
    
    @pytest.mark.asyncio
    async def test_successful_execution_primary_model(self, fallback_chain, router_mock):
        """Test successful execution with primary model"""
        async def mock_executor(model, task):
            return f"Response from {model}"
        
        router_mock.route_request = AsyncMock(return_value=("phi3:mini", {"test": "metadata"}))
        
        result = await fallback_chain.execute_with_fallback(
            "Test task", "planning", mock_executor
        )
        
        assert result["response"] == "Response from phi3:mini"
        assert result["model_used"] == "phi3:mini"
        assert result["primary_model"] == "phi3:mini"
        assert result["fallback_used"] is False
        assert len(result["attempts"]) == 1
        assert result["attempts"][0].success is True
        assert "execution_time" in result
    
    @pytest.mark.asyncio
    async def test_fallback_execution_second_model_succeeds(self, fallback_chain, router_mock):
        """Test fallback execution when primary model fails but second succeeds"""
        call_count = 0
        async def mock_executor(model, task):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call (primary model) fails
                raise Exception("Primary model failed")
            return f"Response from {model}"  # Second call succeeds
        
        router_mock.route_request = AsyncMock(return_value=("phi3:mini", {"test": "metadata"}))
        
        result = await fallback_chain.execute_with_fallback(
            "Test task", "planning", mock_executor
        )
        
        assert result["fallback_used"] is True
        assert result["model_used"] == "llama3.2:1b"  # First fallback model
        assert len(result["attempts"]) == 2
        assert result["attempts"][0].success is False
        assert result["attempts"][0].model == "phi3:mini"
        assert result["attempts"][1].success is True
        assert result["attempts"][1].model == "llama3.2:1b"
    
    @pytest.mark.asyncio
    async def test_all_models_fail(self, fallback_chain, router_mock):
        """Test behavior when all models in chain fail"""
        async def mock_executor(model, task):
            raise Exception(f"{model} failed")
        
        router_mock.route_request = AsyncMock(return_value=("phi3:mini", {"test": "metadata"}))
        
        with pytest.raises(Exception, match="All fallback models failed"):
            await fallback_chain.execute_with_fallback(
                "Test task", "planning", mock_executor
            )
    
    @pytest.mark.asyncio
    async def test_no_fallback_config(self, fallback_chain, router_mock):
        """Test execution when no fallback configuration exists"""
        # Remove fallback config
        router_mock.fallback_configs = {}
        
        async def mock_executor(model, task):
            return f"Response from {model}"
        
        router_mock.route_request = AsyncMock(return_value=("phi3:mini", {"test": "metadata"}))
        
        result = await fallback_chain.execute_with_fallback(
            "Test task", "planning", mock_executor
        )
        
        assert result["fallback_used"] is False
        assert result["model_used"] == "phi3:mini"
        assert len(result["attempts"]) == 1
    
    def test_circuit_breaker_threshold(self, fallback_chain):
        """Test circuit breaker opens after threshold failures"""
        model = "test_model"
        
        # Record failures below threshold
        for _ in range(4):
            fallback_chain._record_failure(model)
        assert fallback_chain._is_circuit_breaker_open(model) is False
        
        # One more failure should open the breaker
        fallback_chain._record_failure(model)
        assert fallback_chain._is_circuit_breaker_open(model) is True
    
    def test_circuit_breaker_reset(self, fallback_chain):
        """Test circuit breaker reset functionality"""
        model = "test_model"
        
        # Open circuit breaker
        for _ in range(5):
            fallback_chain._record_failure(model)
        assert fallback_chain._is_circuit_breaker_open(model) is True
        
        # Reset should close it
        fallback_chain._reset_circuit_breaker(model)
        assert fallback_chain._is_circuit_breaker_open(model) is False
    
    def test_circuit_breaker_timeout(self, fallback_chain):
        """Test circuit breaker timeout functionality"""
        model = "test_model"
        
        # Open circuit breaker
        for _ in range(5):
            fallback_chain._record_failure(model)
        assert fallback_chain._is_circuit_breaker_open(model) is True
        
        # Simulate timeout by modifying last_failure time
        fallback_chain.circuit_breakers[model]["last_failure"] = time.time() - 400  # 400 seconds ago
        
        # Should be closed now due to timeout
        assert fallback_chain._is_circuit_breaker_open(model) is False
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_skips_unhealthy_models(self, fallback_chain, router_mock):
        """Test that circuit breaker skips unhealthy models"""
        # Open circuit breaker for primary model
        for _ in range(5):
            fallback_chain._record_failure("phi3:mini")
        
        async def mock_executor(model, task):
            return f"Response from {model}"
        
        router_mock.route_request = AsyncMock(return_value=("phi3:mini", {"test": "metadata"}))
        
        result = await fallback_chain.execute_with_fallback(
            "Test task", "planning", mock_executor
        )
        
        # Should skip phi3:mini and use first fallback
        assert result["model_used"] == "llama3.2:1b"
        assert result["fallback_used"] is True
    
    def test_fallback_attempt_creation(self):
        """Test FallbackAttempt dataclass creation"""
        attempt = FallbackAttempt(
            model="phi3:mini",
            attempt_number=0,
            start_time=time.time()
        )
        
        assert attempt.model == "phi3:mini"
        assert attempt.attempt_number == 0
        assert attempt.success is False  # Default value
        assert attempt.error is None  # Default value
        assert attempt.response is None  # Default value
    
    def test_get_fallback_status(self, fallback_chain, router_mock):
        """Test fallback status reporting"""
        # Add some circuit breaker data
        fallback_chain._record_failure("test_model")
        
        # Mock router health status
        router_mock.get_model_health_status.return_value = {
            "phi3:mini": {"healthy": True, "success_rate": 0.95}
        }
        
        status = fallback_chain.get_fallback_status()
        
        assert "circuit_breakers" in status
        assert "model_health" in status
        assert "environment" in status
        assert "fallback_configs" in status
        assert status["environment"] == "development"

if __name__ == "__main__":
    pytest.main([__file__])
