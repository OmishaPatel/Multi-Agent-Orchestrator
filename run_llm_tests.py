"""
LLM Integration Test Runner
Run this from the project root to execute LLM integration tests
"""
import os
import sys
import subprocess
import asyncio
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import test utilities
sys.path.insert(0, str(project_root / "tests" / "integration" / "llm_integration"))

async def main():    
    print("LLM Integration Test Runner")
    print("=" * 50)
    
    # Change to the LLM integration test directory
    test_dir = project_root / "tests" / "integration" / "llm_integration"
    os.chdir(test_dir)
    
    print(f"Working directory: {test_dir}")
    print()
    
    # Run pre-flight check
    print("Running pre-flight check...")
    try:
        result = subprocess.run([sys.executable, "check_test_readiness.py"], 
                              capture_output=True, text=True)
        
        print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)
        
        if result.returncode != 0:
            print("[ERROR] Pre-flight check failed. Please fix the issues above.")
            return result.returncode
            
    except Exception as e:
        print(f"[ERROR] Failed to run pre-flight check: {e}")
        return 1
    
    print("\nRunning LLM Integration Tests...")
    print("=" * 50)
    
    # Run the tests
    test_commands = [
        # Basic Ollama integration
        [sys.executable, "-m", "pytest", "test_ollama_integration.py", "-v"],
        
        # Comprehensive LLM tests (skip HuggingFace due to API limitations)
        [sys.executable, "-m", "pytest", "test_llm_integration.py", "-v"],
    ]
    
    all_passed = True
    
    for i, cmd in enumerate(test_commands, 1):
        print(f"\nRunning test batch {i}/{len(test_commands)}...")
        print(f"Command: {' '.join(cmd)}")
        print("-" * 30)
        
        try:
            result = subprocess.run(cmd, text=True)
            
            if result.returncode != 0:
                print(f"[ERROR] Test batch {i} failed with exit code {result.returncode}")
                all_passed = False
            else:
                print(f"[SUCCESS] Test batch {i} passed!")
                
        except Exception as e:
            print(f"[ERROR] Failed to run test batch {i}: {e}")
            all_passed = False
    
    # Summary
    print("\n" + "=" * 50)
    if all_passed:
        print("[SUCCESS] All LLM integration tests passed!")
        return 0
    else:
        print("[ERROR] Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)