#!/usr/bin/env python3
"""
Test runner script for the multi-agent orchestrator project.
Provides convenient commands for running different types of tests.
"""
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle the output."""
    print(f"\n🚀 {description}")
    print("=" * 50)
    
    try:
        # Ensure we're using Poetry for all Python commands
        if not cmd.startswith("poetry run"):
            cmd = f"poetry run {cmd}"
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.stdout:
            print(result.stdout)
        
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode != 0:
            print(f"❌ Command failed with exit code {result.returncode}")
            return False
        else:
            print("✅ Command completed successfully")
            return True
            
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test runner for multi-agent orchestrator")
    parser.add_argument(
        "test_type", 
        choices=["all", "unit", "integration", "fast", "slow", "state", "tools"],
        help="Type of tests to run"
    )
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true", 
        help="Verbose output"
    )
    parser.add_argument(
        "--coverage", "-c", 
        action="store_true", 
        help="Run with coverage report"
    )
    
    args = parser.parse_args()
    
    # Base pytest command
    base_cmd = "python -m pytest"
    
    if args.verbose:
        base_cmd += " -v"
    
    if args.coverage:
        base_cmd += " --cov=src --cov-report=html --cov-report=term-missing"
    
    # Test type specific commands
    commands = {
        "all": f"{base_cmd} tests/",
        "unit": f"{base_cmd} tests/unit/",
        "integration": f"{base_cmd} tests/integration/ -m integration",
        "fast": f"{base_cmd} tests/ -m 'not slow'",
        "slow": f"{base_cmd} tests/ -m slow",
        "state": f"{base_cmd} tests/unit/test_graph/test_state.py",
        "tools": f"{base_cmd} tests/unit/test_tools/"
    }
    
    # Run the selected test type
    cmd = commands[args.test_type]
    success = run_command(cmd, f"Running {args.test_type} tests")
    
    if args.coverage and success:
        print("\n📊 Coverage report generated in htmlcov/index.html")
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()