#!/usr/bin/env python3
"""
Integration test runner for LLM wrappers with pre-flight checks
"""
import asyncio
import sys
import os
import pytest
from check_test_readiness import main as check_readiness

async def run_integration_tests():
    """Run LLM wrapper integration tests with pre-flight checks"""
    
    print("🔍 Pre-flight Check...")
    readiness_code = await check_readiness()
    
    if readiness_code != 0:
        print("\n❌ Pre-flight check failed. Please fix the issues above.")
        return readiness_code
    
    print("\n🧪 Running Integration Tests...")
    print("=" * 50)
    
    # Test configuration
    test_args = [
        "tests/integration/test_llm_integration.py",
        "-v",
        "--tb=short",
        "-m", "integration",
        "--asyncio-mode=auto"
    ]
    
    # Add specific test filters based on available services
    test_filters = []
    
    if os.getenv("TEST_OLLAMA", "").lower() == "true":
        test_filters.append("ollama")
        print("🦙 Ollama tests enabled")
    
    if os.getenv("HUGGINGFACE_API_TOKEN"):
        test_filters.append("huggingface")
        print("🤗 HuggingFace tests enabled")
    
    if os.getenv("TEST_VLLM", "").lower() == "true":
        test_filters.append("vllm")
        print("🚀 vLLM tests enabled")
    
    if not test_filters:
        print("⚠️  No integration tests enabled. Check your environment variables.")
        return 1
    
    # Add test filter
    if len(test_filters) == 1:
        test_args.extend(["-k", test_filters[0]])
    elif len(test_filters) > 1:
        test_args.extend(["-k", " or ".join(test_filters)])
    
    print(f"\n🏃 Running: pytest {' '.join(test_args[1:])}")
    print("=" * 50)
    
    # Run tests
    exit_code = pytest.main(test_args)
    
    if exit_code == 0:
        print("\n🎉 All integration tests passed!")
    else:
        print(f"\n❌ Some tests failed (exit code: {exit_code})")
    
    return exit_code

if __name__ == "__main__":
    exit_code = asyncio.run(run_integration_tests())
    sys.exit(exit_code)