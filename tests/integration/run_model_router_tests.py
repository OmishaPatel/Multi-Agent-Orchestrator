# tests/integration/run_model_router_tests.py
"""
Integration test runner for model router system.
Run this script to execute all model router integration tests.
"""
import sys
import os
import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

def run_integration_tests():
    """Run all model router integration tests"""
    test_files = [
        "tests/integration/test_model_router_integration.py",
        "tests/integration/test_model_service_integration.py"
    ]
    
    print("Running Model Router Integration Tests...")
    print("=" * 50)
    
    # Run tests with verbose output
    exit_code = pytest.main([
        "-v",
        "--tb=short",
        "--color=yes",
        *test_files
    ])
    
    if exit_code == 0:
        print("\n✅ All integration tests passed!")
    else:
        print("\n❌ Some integration tests failed!")
    
    return exit_code

if __name__ == "__main__":
    exit_code = run_integration_tests()
    sys.exit(exit_code)
