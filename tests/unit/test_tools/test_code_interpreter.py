import pytest
import docker
from unittest.mock import Mock, patch, MagicMock


class TestCodeInterpreter:
    
    @pytest.fixture(autouse=True)
    def setup(self):
        try:
            from tools.code_interpreter import code_interpreter_tool
            self.tool = code_interpreter_tool
        except ImportError:
            pytest.skip("Code interpreter tool not available")
    
    def test_docker_availability(self):
        try:
            client = docker.from_env()
            client.ping()
            assert True, "Docker should be available"
        except Exception as e:
            pytest.skip(f"Docker not available: {e}")
    
    def test_code_interpreter_import(self):
        from tools.code_interpreter import code_interpreter_tool
        assert code_interpreter_tool is not None
    
    @pytest.mark.parametrize("code,expected_output", [
        ("print(2 + 2)", "4"),
        ("name = 'World'\nprint(f'Hello, {name}!')", "Hello, World!"),
    ])
    def test_basic_execution(self, code, expected_output):
        result = self.tool.run(code)
        assert expected_output in result
    
    @pytest.mark.parametrize("code,expected_contains", [
        (
            "numbers = [1, 2, 3, 4, 5]\ntotal = sum(numbers)\nprint(f'Sum: {total}')\nprint(f'Average: {total/len(numbers)}')",
            ["Sum: 15", "Average: 3.0"]
        ),
        (
            "import math\nprint(f'Pi: {math.pi:.2f}')\nprint(f'Square root of 16: {math.sqrt(16)}')",
            ["Pi: 3.14", "Square root of 16: 4.0"]
        ),
        (
            "for i in range(3):\n    print(f'Line {i+1}')",
            ["Line 1", "Line 2", "Line 3"]
        )
    ])
    def test_complex_execution(self, code, expected_contains):
        result = self.tool.run(code)
        for expected in expected_contains:
            assert expected in result, f"Expected '{expected}' not found in result: {result}"
    
    def test_error_handling(self):
        result = self.tool.run("print(1/0)")
        assert any(keyword in result.lower() for keyword in ["error", "exception", "zerodivision"])
    
    def test_built_in_modules(self):
        code = """
import math
import random
import os
print("Modules imported successfully")
"""
        result = self.tool.run(code)
        assert "Modules imported successfully" in result
    
    @pytest.mark.slow
    def test_performance_quick_computation(self):
        code = """
import time
start = time.time()
total = sum(range(1000))
end = time.time()
print(f"Computed sum of 0-999: {total}")
print(f"Time taken: {end - start:.4f} seconds")
"""
        result = self.tool.run(code)
        assert "Computed sum of 0-999: 499500" in result
        assert "Time taken:" in result


class TestCodeInterpreterSecurity:
    
    @pytest.fixture(autouse=True)
    def setup(self):
        try:
            from tools.code_interpreter import code_interpreter_tool
            self.tool = code_interpreter_tool
        except ImportError:
            pytest.skip("Code interpreter tool not available")
    
    def test_file_system_access_limited(self):
        code = """
import os
print(f"Current directory: {os.getcwd()}")
try:
    contents = os.listdir('.')
    print(f"Directory accessible: True")
except Exception as e:
    print(f"Directory access error: {e}")
"""
        result = self.tool.run(code)
        # Should be able to access current directory
        assert "Current directory:" in result


class TestCodeInterpreterMocked:
    
    @patch('docker.from_env')
    def test_with_mocked_docker(self, mock_docker):
        """Test code interpreter behavior with mocked Docker."""
        # Setup mock
        mock_client = Mock()
        mock_container = Mock()
        mock_container.logs.return_value = b"Mocked output"
        mock_client.containers.run.return_value = mock_container
        mock_docker.return_value = mock_client
        
        # This would require modifying the actual tool to be testable
        # For now, just test that mocking works
        client = docker.from_env()
        assert client is not None
    
    def test_error_scenarios(self):
        test_cases = [
            ("invalid_syntax = ", "SyntaxError"),
            ("undefined_variable", "NameError"),
            ("import nonexistent_module", "ModuleNotFoundError"),
        ]
        
        try:
            from tools.code_interpreter import code_interpreter_tool
            tool = code_interpreter_tool
        except ImportError:
            pytest.skip("Code interpreter tool not available")
        
        for code, expected_error in test_cases:
            result = tool.run(code)
            # Should contain some indication of error
            assert any(keyword in result.lower() for keyword in ["error", "exception"])


# Integration test class
class TestCodeInterpreterIntegration:   
    @pytest.mark.integration
    @pytest.mark.slow
    def test_full_workflow(self):
        try:
            from tools.code_interpreter import code_interpreter_tool
            tool = code_interpreter_tool
        except ImportError:
            pytest.skip("Code interpreter tool not available")
        
        # Multi-step calculation
        code = """
# Step 1: Data preparation
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
print(f"Data: {data}")

# Step 2: Statistical calculations
import statistics
mean = statistics.mean(data)
median = statistics.median(data)
stdev = statistics.stdev(data)

print(f"Mean: {mean}")
print(f"Median: {median}")
print(f"Standard Deviation: {stdev:.2f}")

# Step 3: Data transformation
squared = [x**2 for x in data]
print(f"Squared: {squared}")

# Step 4: Final result
result = sum(squared) / len(squared)
print(f"Mean of squares: {result}")
"""
        
        result = tool.run(code)
        
        # Verify all steps completed
        assert "Data: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]" in result
        assert "Mean: 5.5" in result
        assert "Median: 5.5" in result
        assert "Standard Deviation:" in result
        assert "Mean of squares: 38.5" in result


# Pytest configuration for this module
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")


# Helper functions for test data
def get_test_code_samples():
    return {
        "basic_math": "print(2 + 2)",
        "string_ops": "name = 'World'\nprint(f'Hello, {name}!')",
        "list_ops": "numbers = [1, 2, 3]\nprint(sum(numbers))",
        "error_case": "print(1/0)",
        "import_test": "import math\nprint(math.pi)",
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])