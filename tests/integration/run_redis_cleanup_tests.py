#!/usr/bin/env python3
"""
Script to run Redis cleanup tests
"""

import subprocess
import sys
import os

def run_unit_tests():
    """Run unit tests for Redis cleanup"""
    print("🧪 Running Redis cleanup unit tests...")
    
    try:
        # Get the project root directory (two levels up from tests/integration/)
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/unit/test_redis_cleanup.py", 
            "-v", "--tb=short"
        ], cwd=project_root, capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ Unit tests passed!")
        else:
            print("❌ Unit tests failed!")
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Failed to run unit tests: {e}")
        return False

def run_manual_tests():
    """Run manual integration tests"""
    print("\n🔧 Running manual Redis cleanup tests...")
    print("Note: This requires a running Redis server on localhost:6379")
    
    response = input("Do you have Redis running and want to run integration tests? (y/N): ")
    
    if response.lower() in ['y', 'yes']:
        try:
            # Get the project root directory (two levels up from tests/integration/)
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            
            result = subprocess.run([
                sys.executable, "tests/integration/test_redis_cleanup_integration.py"
            ], cwd=project_root, text=True)
            
            if result.returncode == 0:
                print("✅ Manual tests completed!")
            else:
                print("❌ Manual tests failed!")
                
            return result.returncode == 0
            
        except Exception as e:
            print(f"❌ Failed to run manual tests: {e}")
            return False
    else:
        print("⏭️  Skipping manual tests")
        return True

def check_dependencies():
    """Check if required dependencies are installed"""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        'redis', 'pytest', 'langgraph', 'apscheduler'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} (missing)")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n⚠️  Missing packages: {', '.join(missing_packages)}")
        print("Install with: poetry install " + " ".join(missing_packages))
        return False
    
    print("✅ All dependencies available!")
    return True

def main():
    """Main test runner"""
    print("🚀 Redis Cleanup Test Runner")
    print("=" * 40)
    
    # Check dependencies first
    if not check_dependencies():
        print("❌ Please install missing dependencies first")
        sys.exit(1)
    
    # Run unit tests
    unit_tests_passed = run_unit_tests()
    
    # Run manual tests if unit tests pass
    if unit_tests_passed:
        manual_tests_passed = run_manual_tests()
        
        if unit_tests_passed and manual_tests_passed:
            print("\n🎉 All tests completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Some tests failed")
            sys.exit(1)
    else:
        print("\n❌ Unit tests failed, skipping manual tests")
        sys.exit(1)

if __name__ == "__main__":
    main()