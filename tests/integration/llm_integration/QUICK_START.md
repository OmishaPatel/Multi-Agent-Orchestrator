# LLM Integration Tests - Quick Start Guide

## 🚀 Quick Setup (5 minutes)

### 1. Start Ollama Server
```bash
# Start Ollama (keep this running)
ollama serve
```

### 2. Pull Required Models
```bash
ollama pull phi3:mini
ollama pull llama3.2:1b
ollama pull qwen2:0.5b
```

### 3. Configure Environment
Add to your `.env` file:
```bash
TEST_OLLAMA=true
OLLAMA_BASE_URL=http://localhost:11434
```

### 4. Run Tests
```bash
# From project root
python run_llm_tests.py

# Or manually
cd tests/integration/llm_integration
python check_test_readiness.py
pytest test_ollama_integration.py -v
pytest test_llm_integration.py -k "not huggingface" -v
```

## ✅ Expected Results

### Pre-flight Check
```
Checking Integration Test Environment...
==================================================
Environment: development
Test Timeout: 60s
Ollama Tests: [ENABLED]
vLLM Tests: [DISABLED]
HuggingFace Token: [AVAILABLE]

Checking Ollama Service...
[OK] Ollama is running at http://localhost:11434
Checking Ollama Models...
  [OK] phi3:mini
  [OK] llama3.2:1b
  [OK] qwen2:0.5b

==================================================
[SUCCESS] All services are ready for integration testing!
```

### Test Results
```
test_ollama_integration.py::TestOllamaIntegration::test_ollama_basic_generation PASSED
test_ollama_integration.py::TestOllamaIntegration::test_ollama_model_availability PASSED
test_ollama_integration.py::TestOllamaIntegration::test_ollama_error_handling PASSED

test_llm_integration.py::TestLLMIntegration::test_ollama_end_to_end PASSED
test_llm_integration.py::TestLLMIntegration::test_retry_logic_integration PASSED
test_llm_integration.py::TestLLMIntegration::test_caching_integration PASSED

[SUCCESS] All LLM integration tests passed!
```

## 🎯 What These Tests Verify

- ✅ Ollama LLM wrapper functionality
- ✅ Model availability checking
- ✅ Text generation with real models
- ✅ Retry logic and error handling
- ✅ Response caching mechanisms
- ✅ Metrics collection and reporting
- ✅ LLM Factory pattern
- ✅ Environment-specific configuration