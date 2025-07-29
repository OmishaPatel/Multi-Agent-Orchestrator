#!/usr/bin/env python3
"""
Pre-test health check script to verify all services are ready
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

# Ensure .env file is loaded
load_dotenv()

from test_config import (
    IntegrationTestConfig,
    check_ollama_health,
    check_vllm_health,
    verify_ollama_models,
    get_test_requirements
)

async def main():
    """Check if integration test environment is ready"""
    print("Checking Integration Test Environment...")
    print("=" * 50)
    
    # Check test requirements
    requirements = get_test_requirements()
    print(f"Environment: {requirements['environment']}")
    print(f"Test Timeout: {requirements['timeout']}s")
    print(f"Ollama Tests: {'[ENABLED]' if requirements['ollama_enabled'] else '[DISABLED]'}")
    print(f"vLLM Tests: {'[ENABLED]' if requirements['vllm_enabled'] else '[DISABLED]'}")
    print(f"HuggingFace Token: {'[AVAILABLE]' if requirements['huggingface_token_available'] else '[MISSING]'}")
    print()
    
    all_good = True
    
    # Check Ollama if enabled
    if requirements['ollama_enabled']:
        print("Checking Ollama Service...")
        ollama_health = await check_ollama_health()
        
        if ollama_health['status'] == 'healthy':
            print(f"[OK] Ollama is running at {ollama_health['url']}")
            
            # Check models
            print("Checking Ollama Models...")
            model_status = await verify_ollama_models()
            
            for model, available in model_status.items():
                status = "[OK]" if available else "[MISSING]"
                print(f"  {status} {model}")
                if not available:
                    print(f"    Run: ollama pull {model}")
                    all_good = False
        else:
            print(f"[ERROR] Ollama is not accessible: {ollama_health.get('error', 'Unknown error')}")
            print("Make sure to run: ollama serve")
            all_good = False
        print()
    
    # Check vLLM if enabled
    if requirements['vllm_enabled']:
        print("Checking vLLM Service...")
        vllm_health = await check_vllm_health()
        
        if vllm_health['status'] == 'healthy':
            print(f"[OK] vLLM is running at {vllm_health['url']}")
        else:
            print(f"[ERROR] vLLM is not accessible: {vllm_health.get('error', 'Unknown error')}")
            print("Make sure vLLM server is running")
            all_good = False
        print()
    
    # Check HuggingFace token
    if not requirements['huggingface_token_available']:
        print("[WARNING] HuggingFace API token not found")
        print("Add HUGGINGFACE_API_TOKEN to your .env file")
        print("Get token from: https://huggingface.co/settings/tokens")
        print()
    
    # Summary
    print("=" * 50)
    if all_good:
        print("[SUCCESS] All services are ready for integration testing!")
        print("\nRun tests with:")
        print("   pytest tests/integration/test_llm_integration.py -v")
        return 0
    else:
        print("[ERROR] Some services need attention before running tests")
        print("\nFix the issues above and run this script again")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)