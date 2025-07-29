"""
Integration test configuration and utilities
"""
import os
import asyncio
import aiohttp
from typing import Dict, Any
from dotenv import load_dotenv

# Ensure .env file is loaded
load_dotenv()

class IntegrationTestConfig:
    """Configuration for integration tests"""
    
    # Service URLs
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000")
    
    # API Tokens
    HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")
    VLLM_API_KEY = os.getenv("VLLM_API_KEY", "dummy-key")
    
    # Test Flags
    TEST_OLLAMA = os.getenv("TEST_OLLAMA", "").lower() == "true"
    TEST_VLLM = os.getenv("TEST_VLLM", "").lower() == "true"
    
    # Test Settings
    TEST_TIMEOUT = int(os.getenv("TEST_TIMEOUT", "60"))
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

async def check_service_health(url: str, endpoint: str = "/health") -> Dict[str, Any]:
    """Check if a service is healthy and accessible"""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(f"{url}{endpoint}") as response:
                if response.status == 200:
                    return {"status": "healthy", "url": url}
                else:
                    return {"status": "unhealthy", "url": url, "status_code": response.status}
    except Exception as e:
        return {"status": "unreachable", "url": url, "error": str(e)}

async def check_ollama_health() -> Dict[str, Any]:
    """Check Ollama service health"""
    return await check_service_health(IntegrationTestConfig.OLLAMA_BASE_URL, "/api/tags")

async def check_vllm_health() -> Dict[str, Any]:
    """Check vLLM service health"""
    return await check_service_health(IntegrationTestConfig.VLLM_BASE_URL, "/health")

async def verify_ollama_models() -> Dict[str, bool]:
    """Verify required Ollama models are available"""
    required_models = ["phi3:mini", "llama3.2:1b", "qwen2:0.5b"]
    model_status = {}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{IntegrationTestConfig.OLLAMA_BASE_URL}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    available_models = [model["name"] for model in data.get("models", [])]
                    
                    for model in required_models:
                        model_status[model] = model in available_models
                else:
                    for model in required_models:
                        model_status[model] = False
    except Exception:
        for model in required_models:
            model_status[model] = False
    
    return model_status

def get_test_requirements() -> Dict[str, Any]:
    """Get summary of test requirements and their status"""
    return {
        "ollama_enabled": IntegrationTestConfig.TEST_OLLAMA,
        "vllm_enabled": IntegrationTestConfig.TEST_VLLM,
        "huggingface_token_available": bool(IntegrationTestConfig.HUGGINGFACE_API_TOKEN),
        "environment": IntegrationTestConfig.ENVIRONMENT,
        "timeout": IntegrationTestConfig.TEST_TIMEOUT
    }