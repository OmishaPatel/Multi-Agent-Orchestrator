"""
Quick test runner for monitoring integration

Prerequisites:
1. Ollama server running: ollama serve
2. At least one model available: ollama pull phi3:mini

Usage:
    python tests/integration/llm_integration/run_monitoring_test.py
"""

import asyncio
import sys
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

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from core.monitoring.model_monitor import SimpleModelMonitor
from core.llm_wrappers.monitored_llm import SimpleMonitoredLLM

async def check_ollama_server():
    """Check if Ollama server is running and get available models"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:11434/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    models = [model["name"] for model in data.get("models", [])]
                    return True, models
                else:
                    return False, []
    except Exception as e:
        print(f"Error connecting to Ollama: {e}")
        return False, []

async def test_monitoring_integration():
    """Test monitoring integration with real Ollama"""
    print("🚀 Testing Monitoring Integration")
    print("=" * 40)
    
    # Check Ollama server
    print("Checking Ollama server...")
    is_available, models = await check_ollama_server()
    
    if not is_available:
        print("✗ Ollama server not available at localhost:11434")
        print("Please start Ollama server with: ollama serve")
        return False
    
    if not models:
        print("✗ No models available in Ollama")
        print("Please pull a model with: ollama pull phi3:mini")
        return False
    
    print(f"✓ Ollama server available with models: {models}")
    test_model = models[0]
    print(f"Using model: {test_model}")
    print()
    
    # Create temporary storage
    temp_dir = tempfile.mkdtemp()
    try:
        # Create monitor
        print("Creating monitor...")
        monitor = SimpleModelMonitor(
            storage_path=temp_dir,
            max_metrics_memory=50,
            drift_detection_window=5
        )
        monitor.start_monitoring()
        print("✓ Monitor started")
        
        # Create monitored LLM
        print("Creating monitored LLM...")
        llm = SimpleMonitoredLLM(
            model_name=test_model,
            agent_type="planning",
            model_monitor=monitor,
            base_url="http://localhost:11434",
            timeout=30.0
        )
        print("✓ Monitored LLM created")
        
        # Test inference
        print("Testing inference...")
        try:
            response = await llm._acall("Say hello in one word", max_tokens=5)
            print(f"✓ Model response: '{response}'")
        except Exception as e:
            print(f"✗ Inference failed: {e}")
            return False
        
        # Check monitoring data
        print("Checking monitoring data...")
        await asyncio.sleep(1)  # Allow monitoring to process
        
        stats = monitor.get_model_performance(test_model)
        model_key = f"{test_model}_development"
        
        if model_key in stats["models"]:
            model_stats = stats["models"][model_key]
            print(f"✓ Captured {model_stats['total_requests']} requests")
            print(f"✓ Average latency: {model_stats['avg_latency']:.2f}s")
            print(f"✓ Success rate: {(1-model_stats['error_rate'])*100:.1f}%")
        else:
            print("✗ No monitoring data captured")
            return False
        
        # Test simple stats
        simple_stats = llm.get_simple_stats()
        print(f"✓ Simple stats available for {simple_stats['model_name']}")
        
        # Test resource monitoring
        print("Checking resource monitoring...")
        await asyncio.sleep(12)  # Wait for resource collection
        resource_stats = monitor.get_resource_usage()
        
        if "cpu" in resource_stats and "memory" in resource_stats:
            print(f"✓ CPU usage: {resource_stats['cpu']['current']:.1f}%")
            print(f"✓ Memory usage: {resource_stats['memory']['current']:.1f}%")
        else:
            print("✗ Resource monitoring not working")
            return False
        
        # Test multiple calls
        print("Testing multiple calls...")
        for i in range(3):
            try:
                await llm._acall(f"Say number {i+1}", max_tokens=5)
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Call {i+1} failed: {e}")
        
        # Final stats
        final_stats = monitor.get_model_performance(test_model)
        if model_key in final_stats["models"]:
            final_model_stats = final_stats["models"][model_key]
            print(f"✓ Final total requests: {final_model_stats['total_requests']}")
        
        # Check alerts
        alerts = monitor.get_alerts()
        if alerts:
            print(f"⚠️  Generated {len(alerts)} alerts")
        else:
            print("✓ No alerts generated")
        
        
        monitor.stop_monitoring()
        print("\n🎉 All monitoring integration tests passed!")
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        shutil.rmtree(temp_dir)

async def main():
    """Main test runner"""
    success = await test_monitoring_integration()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())