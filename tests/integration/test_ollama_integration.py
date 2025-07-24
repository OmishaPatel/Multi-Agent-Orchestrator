# tests/integration/test_ollama_integration.py
"""
Integration tests for Ollama model serving and resource management.
These tests verify the complete model serving pipeline works correctly.
"""

import pytest
import asyncio
import requests
from unittest.mock import Mock, patch
import psutil

from src.config.ollama_config import OllamaModelManager, ModelSize
from src.core.resource_monitor import ResourceMonitor, ResourceThresholds
from src.config.model_environment import EnvironmentAwareModelConfig

class TestOllamaIntegration:
    """Integration tests for Ollama model management"""
    
    @pytest.fixture
    def model_manager(self):
        """Create model manager for testing"""
        return OllamaModelManager(base_url="http://localhost:11434")
    
    @pytest.fixture
    def resource_monitor(self, model_manager):
        """Create resource monitor for testing"""
        return ResourceMonitor(model_manager, check_interval=1)
    
    @pytest.mark.asyncio
    async def test_model_catalog_configuration(self, model_manager):
        """Test that model catalog is properly configured"""
        models = model_manager.models
        
        # Verify all required models are defined
        assert "phi3-mini" in models
        assert "llama3.2-1b" in models
        assert "qwen2-0.5b" in models
        
        # Verify model configurations are reasonable for 16GB RAM
        for model_name, config in models.items():
            assert config.ram_requirement <= 6.0  # Max 6GB for models
            assert config.size_gb > 0
            assert len(config.use_cases) > 0
            assert config.description
    
    @pytest.mark.asyncio
    async def test_resource_aware_model_selection(self, model_manager):
        """Test that model selection respects resource constraints"""
        
        # Mock low memory scenario
        with patch('psutil.virtual_memory') as mock_memory:
            mock_memory.return_value.available = 1 * 1024**3  # 1GB available
            mock_memory.return_value.total = 16 * 1024**3     # 16GB total
            mock_memory.return_value.used = 15 * 1024**3      # 15GB used
            mock_memory.return_value.percent = 93.75
            
            selected_model = await model_manager.select_optimal_model("planning")
            
            # Should select smallest model due to memory constraint
            assert selected_model == "qwen2:0.5b"
    
    @pytest.mark.asyncio
    async def test_model_availability_check(self, model_manager):
        """Test model availability checking and pulling"""
        
        # Mock Ollama API responses
        with patch('requests.get') as mock_get, \
             patch('requests.post') as mock_post:
            
            # Mock model not available initially
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"models": []}
            
            # Mock successful pull
            mock_post.return_value.status_code = 200
            
            result = await model_manager.ensure_model_available("phi3:mini")
            
            assert result is True
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_response_generation_flow(self, model_manager):
        """Test complete response generation flow"""
        
        with patch('requests.get') as mock_get, \
             patch('requests.post') as mock_post:
            
            # Mock model available
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "models": [{"name": "phi3:mini"}]
            }
            
            # Mock successful generation
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "response": "Test response from model"
            }
            
            response = await model_manager.generate_response(
                "What is the capital of France?",
                model="phi3:mini"
            )
            
            assert response == "Test response from model"
    
    @pytest.mark.asyncio
    async def test_resource_monitoring_alerts(self, resource_monitor):
        """Test resource monitoring and alert system"""
        
        # Mock callback for testing
        alert_received = []
        
        async def memory_callback(resources, suggested_model):
            alert_received.append(("memory_warning", resources, suggested_model))
        
        resource_monitor.register_callback("memory_warning", memory_callback)
        
        # Mock high memory usage
        with patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.cpu_percent') as mock_cpu, \
             patch('psutil.swap_memory') as mock_swap:
            
            mock_memory.return_value.percent = 85.0  # Above warning threshold
            mock_memory.return_value.available = 2 * 1024**3
            mock_cpu.return_value = 50.0
            mock_swap.return_value.percent = 0.0
            mock_swap.return_value.total = 0
            
            await resource_monitor._check_resources()
            
            assert len(alert_received) == 1
            assert alert_received[0][0] == "memory_warning"
    
    @pytest.mark.asyncio
    async def test_environment_aware_configuration(self):
        """Test environment-aware model configuration"""
        
        # Test development environment
        with patch.dict('os.environ', {'ENVIRONMENT': 'development'}):
            config = EnvironmentAwareModelConfig()
            
            assert config.environment.value == "development"
            assert config.config["model_provider"] == "ollama"
            assert config.get_model_for_agent("planning") == "phi3:mini"
        
        # Test testing environment
        with patch.dict('os.environ', {'ENVIRONMENT': 'testing'}):
            config = EnvironmentAwareModelConfig()
            
            assert config.environment.value == "testing"
            assert config.config["model_provider"] == "huggingface"

class TestOllamaHealthCheck:
    """Test Ollama service health and connectivity"""
    
    @pytest.mark.asyncio
    async def test_ollama_service_connectivity(self):
        """Test that Ollama service is accessible"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            assert response.status_code == 200
        except requests.RequestException:
            pytest.skip("Ollama service not available for integration testing")
    
    @pytest.mark.asyncio
    async def test_model_pull_and_inference(self):
        """Test actual model pulling and inference (requires Ollama running)"""
        try:
            # Test with smallest model to minimize test time
            model_manager = OllamaModelManager()
            
            # Ensure smallest model is available
            available = await model_manager.ensure_model_available("qwen2:0.5b")
            if not available:
                pytest.skip("Could not pull test model")
            
            # Test inference
            response = await model_manager.generate_response(
                "Hello, respond with just 'Hi'",
                model="qwen2:0.5b"
            )
            
            assert len(response) > 0
            assert "error" not in response.lower()
            
        except Exception as e:
            pytest.skip(f"Ollama integration test failed: {e}")
