#!/usr/bin/env python3
"""
Test script for the Docker-based code interpreter.
Run this to verify everything is working correctly.
"""

import sys
import os
import logging
import docker

# Add src to path so we can import our modules
sys.path.insert(0, 'src')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_docker_availability():
    """Test if Docker is available and working."""
    print("🔍 Testing Docker availability...")
    try:
        client = docker.from_env()
        client.ping()
        print("✅ Docker is available and running")
        return True
    except Exception as e:
        print(f"❌ Docker not available: {e}")
        return False

def test_code_interpreter_import():
    """Test if we can import the code interpreter."""
    print("\n🔍 Testing code interpreter import...")
    try:
        from tools.code_interpreter import code_interpreter_tool
        print("✅ Code interpreter imported successfully")
        return code_interpreter_tool
    except Exception as e:
        print(f"❌ Failed to import code interpreter: {e}")
        return None

def run_test_cases(tool):
    """Run various test cases."""
    print("\n🧪 Running test cases...")
    
    test_cases = [
        {
            "name": "Basic Math",
            "code": "print(2 + 2)",
            "expected_output": "4"
        },
        {
            "name": "String Operations",
            "code": """
name = "World"
print(f"Hello, {name}!")
""",
            "expected_output": "Hello, World!"
        },
        {
            "name": "List Operations",
            "code": """
numbers = [1, 2, 3, 4, 5]
total = sum(numbers)
print(f"Sum: {total}")
print(f"Average: {total/len(numbers)}")
""",
            "expected_contains": ["Sum: 15", "Average: 3.0"]
        },
        {
            "name": "Built-in Modules",
            "code": """
import math
import random

print(f"Pi: {math.pi:.2f}")
print(f"Square root of 16: {math.sqrt(16)}")
random.seed(42)  # For reproducible results
print(f"Random number: {random.randint(1, 10)}")
""",
            "expected_contains": ["Pi: 3.14", "Square root of 16: 4.0"]
        },
        {
            "name": "Error Handling",
            "code": "print(1/0)",  # This should cause an error
            "should_error": True
        },
        {
            "name": "Multiple Print Statements",
            "code": """
for i in range(3):
    print(f"Line {i+1}")
""",
            "expected_contains": ["Line 1", "Line 2", "Line 3"]
        }
    ]
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n  Test {i}: {test['name']}")
        print(f"  Code: {test['code'].strip()}")
        
        try:
            result = tool.run(test['code'])
            print(f"  Result: {result}")
            
            # Check if test should error
            if test.get('should_error', False):
                if "Error" in result or "error" in result.lower():
                    print("  ✅ Error handled correctly")
                    passed += 1
                else:
                    print("  ❌ Expected error but got success")
                    failed += 1
            # Check exact output
            elif 'expected_output' in test:
                if test['expected_output'] in result:
                    print("  ✅ Output matches expected")
                    passed += 1
                else:
                    print(f"  ❌ Expected '{test['expected_output']}' but got '{result}'")
                    failed += 1
            # Check if result contains expected strings
            elif 'expected_contains' in test:
                all_found = all(expected in result for expected in test['expected_contains'])
                if all_found:
                    print("  ✅ All expected strings found")
                    passed += 1
                else:
                    missing = [exp for exp in test['expected_contains'] if exp not in result]
                    print(f"  ❌ Missing expected strings: {missing}")
                    failed += 1
            else:
                print("  ✅ Executed without error")
                passed += 1
                
        except Exception as e:
            print(f"  ❌ Exception during execution: {e}")
            failed += 1
    
    print(f"\n📊 Test Results: {passed} passed, {failed} failed")
    return passed, failed

def test_security_features():
    """Test security-related features."""
    print("\n🔒 Testing security features...")
    
    security_tests = [
        {
            "name": "Network Access (should fail)",
            "code": """
import urllib.request
try:
    response = urllib.request.urlopen('http://httpbin.org/get', timeout=5)
    print("Network access succeeded (BAD!)")
except Exception as e:
    print(f"Network access blocked (GOOD): {type(e).__name__}")
""",
            "expected_contains": ["Network access blocked"]
        },
        {
            "name": "File System Access (limited)",
            "code": """
import os
print(f"Current directory: {os.getcwd()}")
print(f"Directory contents: {os.listdir('.')}")
""",
            "should_work": True
        }
    ]
    
    for test in security_tests:
        print(f"\n  Security Test: {test['name']}")
        try:
            from tools.code_interpreter import code_interpreter_tool
            result = code_interpreter_tool.run(test['code'])
            print(f"  Result: {result}")
            
            if 'expected_contains' in test:
                found = any(expected in result for expected in test['expected_contains'])
                if found:
                    print("  ✅ Security feature working")
                else:
                    print("  ⚠️ Security feature may not be working as expected")
                    
        except Exception as e:
            print(f"  ❌ Error in security test: {e}")

def performance_test():
    """Test performance and timeout."""
    print("\n⏱️ Testing performance and timeout...")
    
    # Test that should complete quickly
    quick_test = """
import time
start = time.time()
total = sum(range(1000))
end = time.time()
print(f"Computed sum of 0-999: {total}")
print(f"Time taken: {end - start:.4f} seconds")
"""
    
    try:
        from tools.code_interpreter import code_interpreter_tool
        
        print("  Quick computation test:")
        result = code_interpreter_tool.run(quick_test)
        print(f"  Result: {result}")
            
    except Exception as e:
        print(f"  ❌ Performance test error: {e}")

def main():
    """Main test function."""
    print("🚀 Starting Docker Code Interpreter Tests")
    print("=" * 50)
    
    # Test 1: Docker availability
    docker_available = test_docker_availability()
    
    # Test 2: Import
    tool = test_code_interpreter_import()
    if not tool:
        print("\n❌ Cannot proceed without code interpreter")
        return
    
    # Test 3: Basic functionality
    passed, failed = run_test_cases(tool)
    
    # Test 4: Security features
    if docker_available:
        test_security_features()
        performance_test()
    else:
        print("\n⚠️ Skipping security and performance tests (Docker not available)")
    
    # Summary
    print("\n" + "=" * 50)
    print("🏁 Test Summary")
    print(f"Docker Available: {'✅' if docker_available else '❌'}")
    print(f"Basic Tests: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Your code interpreter is working correctly.")
    else:
        print("⚠️ Some tests failed. Please check the output above.")

if __name__ == "__main__":
    main() 