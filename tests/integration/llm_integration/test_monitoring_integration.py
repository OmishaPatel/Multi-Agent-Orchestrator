import pytest
import asyncio
import time
import tempfile
import shutil
from pathlib import Path
import aiohttp
import warnings

# Suppress all deprecation and user warnings to clean up test output
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*Pydantic.*")
warnings.filterwarnings("ignore", message=".*pkg_resources.*")
warnings.filterwarnings("ignore", message=".*google.*")
warnings.filterwarnings("ignore", message=".*mlflow.*")

from src.core.monitoring.model_monitor import SimpleModelMonitor, SimpleInferenceMetric
from src.core.monitoring.mlflow import SimpleMLflowTracker
from src.core.llm_wrappers.monitored_llm import SimpleMonitoredLLM
from src.core.llm_wrappers.ollama_llm import OllamaLLM
import mlflow

class TestSimpleMonitoringIntegration:
    """Integration tests for simplified monitoring system with real Ollama"""
    
    @pytest.fixture
    def temp_storage_path(self):
        """Create temporary storage for test data"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def simple_monitor(self, temp_storage_path):
        """Create SimpleModelMonitor with temporary storage"""
        monitor = SimpleModelMonitor(
            storage_path=temp_storage_path,
            max_metrics_memory=100,  # Small for testing
            drift_detection_window=10  # Small window for testing
        )
        yield monitor
        monitor.stop_monitoring()
    
    @pytest.fixture
    async def ollama_availability(self):
        """Check if Ollama server is available"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:11434/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        models = await response.json()
                        available_models = [model["name"] for model in models.get("models", [])]
                        return True, available_models
        except Exception as e:
            return False, []
        return False, []
    
    @pytest.fixture
    def test_model_name(self):
        """Default test model - commonly available lightweight model"""
        return "phi3:mini"  # Fallback to any available model in real test
    
    @pytest.mark.asyncio
    async def test_ollama_server_connection(self, ollama_availability):
        """Test that Ollama server is accessible"""
        is_available, models = await ollama_availability
        
        if not is_available:
            pytest.skip("Ollama server not available at localhost:11434")
        
        assert is_available, "Ollama server should be accessible"
        assert len(models) > 0, "At least one model should be available"
        print(f"Available models: {models}")
    
    @pytest.mark.asyncio
    async def test_simple_monitor_basic_functionality(self, simple_monitor):
        """Test basic monitoring functionality without real LLM calls"""
        # Test monitoring start/stop
        simple_monitor.start_monitoring()
        assert simple_monitor._monitoring_active
        
        # Test manual metric recording
        simple_monitor.record_inference(
            model_name="test-model",
            agent_type="planning",
            environment="development",
            total_tokens=50,
            latency=1.5,
            success=True
        )
        
        # Verify metrics were recorded
        stats = simple_monitor.get_model_performance("test-model")
        assert "test-model_development" in stats["models"]
        
        model_stats = stats["models"]["test-model_development"]
        assert model_stats["total_requests"] == 1
        assert model_stats["successful_requests"] == 1
        assert model_stats["error_rate"] == 0.0
        assert model_stats["avg_latency"] == 1.5
        
        # Test summary
        summary = simple_monitor.get_summary()
        assert summary["total_requests"] == 1
        assert summary["total_errors"] == 0
        assert summary["active_models"] == 1
        
        simple_monitor.stop_monitoring()
        assert not simple_monitor._monitoring_active
    
    @pytest.mark.asyncio
    async def test_resource_monitoring(self, simple_monitor):
        """Test resource monitoring functionality"""
        simple_monitor.start_monitoring()
        
        # Wait for at least one resource collection cycle
        await asyncio.sleep(12)  # Resource monitoring runs every 10 seconds
        
        # Check resource metrics were collected
        resource_stats = simple_monitor.get_resource_usage(time_window_minutes=1)
        
        assert "cpu" in resource_stats
        assert "memory" in resource_stats
        assert resource_stats["cpu"]["current"] >= 0
        assert resource_stats["memory"]["current"] >= 0
        
        # Verify no GPU metrics (since we removed GPU monitoring)
        assert "gpu" not in resource_stats
        
        simple_monitor.stop_monitoring()
    
    @pytest.mark.asyncio
    async def test_monitored_llm_with_real_ollama(self, simple_monitor, ollama_availability):
        """Test SimpleMonitoredLLM with real Ollama server"""
        is_available, models = await ollama_availability
        
        if not is_available or not models:
            pytest.skip("Ollama server not available or no models found")
        
        # Use first available model
        test_model = models[0]
        print(f"Testing with model: {test_model}")
        
        # Create monitored LLM wrapper
        monitored_llm = SimpleMonitoredLLM(
            model_name=test_model,
            agent_type="planning",
            model_monitor=simple_monitor,
            enable_mlflow=False,  # Keep it simple for testing
            base_url="http://localhost:11434",
            timeout=30.0
        )
        
        simple_monitor.start_monitoring()
        
        # Test successful inference
        test_prompt = "Hello, respond with just 'Hi there!'"
        
        try:
            response = await monitored_llm._acall(test_prompt, max_tokens=10)
            
            # Verify response
            assert isinstance(response, str)
            assert len(response) > 0
            print(f"Model response: {response}")
            
            # Verify monitoring captured the inference
            await asyncio.sleep(1)  # Allow monitoring to process
            stats = simple_monitor.get_model_performance(test_model)
            assert f"{test_model}_development" in stats["models"]
            
            model_stats = stats["models"][f"{test_model}_development"]
            assert model_stats["total_requests"] >= 1
            assert model_stats["successful_requests"] >= 1
            assert model_stats["avg_latency"] > 0
            assert model_stats["tokens_per_second"] > 0
            
            # Test simple stats method
            simple_stats = monitored_llm.get_simple_stats()
            assert simple_stats["model_name"] == test_model
            assert simple_stats["agent_type"] == "planning"
            assert simple_stats["environment"] == "development"
            
            print("✓ Monitoring integration test passed!")
            
        except Exception as e:
            pytest.fail(f"Real Ollama inference failed: {e}")
        
        finally:
            simple_monitor.stop_monitoring()
    
    @pytest.mark.asyncio
    async def test_multiple_inferences_and_drift_detection(self, simple_monitor, ollama_availability):
        """Test multiple inferences and drift detection"""
        is_available, models = await ollama_availability
        
        if not is_available or not models:
            pytest.skip("Ollama server not available or no models found")
        
        test_model = models[0]
        
        monitored_llm = SimpleMonitoredLLM(
            model_name=test_model,
            agent_type="research",
            model_monitor=simple_monitor,
            base_url="http://localhost:11434",
            timeout=30.0
        )
        
        simple_monitor.start_monitoring()
        
        # Perform multiple inferences to test drift detection
        test_prompts = [
            "Say 'one'",
            "Say 'two'", 
            "Say 'three'",
            "Say 'four'",
            "Say 'five'"
        ]
        
        successful_calls = 0
        for i, prompt in enumerate(test_prompts):
            try:
                response = await monitored_llm._acall(prompt, max_tokens=5)
                successful_calls += 1
                print(f"Call {i+1}: {response}")
                
                # Small delay between calls
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"Call {i+1} failed: {e}")
        
        # Verify multiple inferences were recorded
        await asyncio.sleep(1)  # Allow monitoring to process
        stats = simple_monitor.get_model_performance(test_model)
        model_key = f"{test_model}_development"
        
        if model_key in stats["models"]:
            model_stats = stats["models"][model_key]
            assert model_stats["total_requests"] >= successful_calls
            assert model_stats["successful_requests"] >= successful_calls
            
            print(f"✓ Recorded {model_stats['total_requests']} requests")
            print(f"✓ Average latency: {model_stats['avg_latency']:.2f}s")
            print(f"✓ Tokens per second: {model_stats['tokens_per_second']:.1f}")
        
        # Check for any alerts generated
        alerts = simple_monitor.get_alerts()
        print(f"Generated {len(alerts)} alerts")
        
        simple_monitor.stop_monitoring()

    @pytest.mark.asyncio
    async def test_mlflow_integration_basic(self, temp_storage_path):
        """Test basic MLflow integration functionality"""
        # Create MLflow tracker with temporary storage
        mlflow_tracker = SimpleMLflowTracker(
            tracking_uri=f"file://{temp_storage_path}/mlflow",
            experiment_name="test-monitoring-integration"
        )
        
        # Test starting and ending runs
        run_id = mlflow_tracker.start_run("test-run")
        assert run_id is not None
        print(f"Started MLflow run: {run_id}")
        
        # Test logging model info
        mlflow_tracker.log_model_info("phi3:mini", "development", "planning")
        
        # Test logging basic metrics
        mlflow_tracker.log_basic_metrics({
            "latency": 2.5,
            "total_tokens": 100,
            "tokens_per_second": 40.0
        })
        
        # End run
        mlflow_tracker.end_run()
        print("✓ Basic MLflow integration test passed")
    
    @pytest.mark.asyncio
    async def test_monitored_llm_with_mlflow(self, simple_monitor, ollama_availability, temp_storage_path):
        """Test SimpleMonitoredLLM with MLflow enabled"""
        is_available, models = await ollama_availability
        
        if not is_available or not models:
            pytest.skip("Ollama server not available or no models found")
        
        test_model = models[0]
        print(f"Testing MLflow integration with model: {test_model}")
        
        # Create monitored LLM with MLflow enabled
        monitored_llm = SimpleMonitoredLLM(
            model_name=test_model,
            agent_type="planning",
            model_monitor=simple_monitor,
            enable_mlflow=True,  # Enable MLflow for this test
            base_url="http://localhost:11434",
            timeout=30.0
        )
        
        # Override MLflow tracker with test configuration
        monitored_llm.mlflow_tracker = SimpleMLflowTracker(
            tracking_uri=f"file://{temp_storage_path}/mlflow",
            experiment_name="test-ollama-integration"
        )
        
        simple_monitor.start_monitoring()
        
        try:
            # Test inference with MLflow logging
            response = await monitored_llm._acall("Say hello briefly", max_tokens=10)
            
            # Verify response
            assert isinstance(response, str)
            assert len(response) > 0
            print(f"Model response: {response}")
            
            # Verify monitoring captured the inference
            await asyncio.sleep(1)
            stats = simple_monitor.get_model_performance(test_model)
            assert f"{test_model}_development" in stats["models"]
            
            # Test simple stats with MLflow
            simple_stats = monitored_llm.get_simple_stats()
            assert simple_stats["model_name"] == test_model
            
            print("✓ MLflow-enabled monitoring test passed!")
            
        finally:
            simple_monitor.stop_monitoring()
    
    @pytest.mark.asyncio
    async def test_mlflow_experiment_tracking(self, temp_storage_path, ollama_availability):
        """Test MLflow experiment tracking with multiple runs"""
        is_available, models = await ollama_availability
        
        if not is_available or not models:
            pytest.skip("Ollama server not available or no models found")
        
        test_model = models[0]
        
        # Create MLflow tracker
        mlflow_tracker = SimpleMLflowTracker(
            tracking_uri=f"file://{temp_storage_path}/mlflow",
            experiment_name="test-experiment-tracking"
        )
        
        # Create monitor and LLM
        monitor = SimpleModelMonitor(storage_path=f"{temp_storage_path}/monitoring")
        monitor.start_monitoring()
        
        try:
            # Run multiple experiments
            for i in range(3):
                run_id = mlflow_tracker.start_run(f"experiment-run-{i+1}")
                
                # Log model configuration
                mlflow_tracker.log_model_info(test_model, "development", "planning")
                
                # Simulate different performance metrics
                mlflow_tracker.log_basic_metrics({
                    "latency": 2.0 + i * 0.5,
                    "total_tokens": 50 + i * 10,
                    "tokens_per_second": 25.0 - i * 2
                })
                
                mlflow_tracker.end_run()
                print(f"✓ Completed experiment run {i+1}")
            
            print("✓ MLflow experiment tracking test passed!")
            
        finally:
            monitor.stop_monitoring()
    
    @pytest.mark.asyncio
    async def test_mlflow_error_handling(self, temp_storage_path):
        """Test MLflow error handling and graceful degradation"""
        # Test with invalid tracking URI
        mlflow_tracker = SimpleMLflowTracker(
            tracking_uri="invalid://path",
            experiment_name="test-error-handling"
        )
        
        # These should not raise exceptions
        run_id = mlflow_tracker.start_run("error-test")
        mlflow_tracker.log_model_info("test-model", "development", "planning")
        mlflow_tracker.log_basic_metrics({"latency": 1.0})
        mlflow_tracker.end_run()
        
        print("✓ MLflow error handling test passed!")
    
    @pytest.mark.asyncio
    async def test_monitoring_without_mlflow(self, simple_monitor, ollama_availability):
        """Test that monitoring works when MLflow is disabled"""
        is_available, models = await ollama_availability
        
        if not is_available or not models:
            pytest.skip("Ollama server not available or no models found")
        
        test_model = models[0]
        
        # Create monitored LLM with MLflow explicitly disabled
        monitored_llm = SimpleMonitoredLLM(
            model_name=test_model,
            agent_type="planning",
            model_monitor=simple_monitor,
            enable_mlflow=False,  # Explicitly disable MLflow
            base_url="http://localhost:11434",
            timeout=30.0
        )
        
        simple_monitor.start_monitoring()
        
        try:
            # Test inference without MLflow
            response = await monitored_llm._acall("Say hi", max_tokens=5)
            
            # Verify monitoring still works
            await asyncio.sleep(1)
            stats = simple_monitor.get_model_performance(test_model)
            assert f"{test_model}_development" in stats["models"]
            
            print("✓ Monitoring without MLflow test passed!")
            
        finally:
            simple_monitor.stop_monitoring()