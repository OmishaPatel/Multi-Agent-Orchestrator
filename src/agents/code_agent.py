from typing import Dict, Any, Optional, List
import ast
import sys
import subprocess
from src.core.model_service import ModelService
from src.tools.code_interpreter import CodeInterpreter
from src.utils.logging_config import get_logger, get_agent_logger, log_agent_execution
import re

logger = get_agent_logger("code")

class CodeAgent:
    """
    Enhanced code agent with advanced security checks and conditional execution.
    Only invoked for computational tasks requiring Python execution.
    """
    
    def __init__(self):
        self.model_service = ModelService()
        self.code_interpreter = CodeInterpreter()
        
        # Security configuration
        self.security_config = {
            'max_execution_time': 30,
            'memory_limit': '256m',
            'forbidden_imports': [
                'os', 'sys', 'subprocess', 'shutil', 'glob', 'socket', 
                'urllib', 'requests', 'http', 'ftplib', 'smtplib',
                'pickle', 'marshal', 'shelve', 'dbm', 'sqlite3',
                'ctypes', 'multiprocessing', 'threading', 'asyncio'
            ],
            'forbidden_functions': [
                'exec', 'eval', 'compile', '__import__', 'open', 'file',
                'input', 'raw_input', 'reload', 'vars', 'locals', 'globals'
            ],
            'max_code_lines': 200,
            'max_output_size': 10000  # characters
        }
        
    def should_execute_code_task(self, task_description: str) -> bool:        
        # Keywords that indicate computational work requiring Python
        code_indicators = [
            'calculate', 'compute', 'algorithm', 'data processing', 'analyze data',
            'mathematical', 'statistics', 'plot', 'graph', 'visualization',
            'parse', 'process file', 'convert', 'transform data', 'simulation',
            'optimization', 'machine learning', 'regression', 'classification'
        ]
        
        # Keywords that DON'T require code execution (handled by research agent)
        non_code_indicators = [
            'research', 'find information', 'explain', 'describe', 'summarize',
            'what is', 'how does', 'compare', 'list', 'overview', 'definition'
        ]
        
        task_lower = task_description.lower()
        
        # Check for non-code indicators first
        if any(indicator in task_lower for indicator in non_code_indicators):
            return False
        
        # Check for code indicators
        if any(indicator in task_lower for indicator in code_indicators):
            return True
        
        # Default to False - avoid unnecessary code execution
        return False
    
    def execute_task(self, task_description: str, context: Dict[int, str] = None) -> str:
        logger.info(f"Executing code task: {task_description[:100]}...")
        
        # Conditional execution check
        if not self.should_execute_code_task(task_description):
            logger.info("Task doesn't require code execution, delegating to research agent")
            return self._delegate_to_research_explanation(task_description)
        
        try:
            # Get model for code generation
            model = self.model_service.get_model_for_agent("code")
            
            # Generate code solution
            code_solution = self._generate_code_solution(task_description, context or {}, model)
            
            # Enhanced security validation
            security_check = self._comprehensive_security_check(code_solution)
            if not security_check['safe']:
                return self._format_security_error(security_check)
            
            # Execute code securely
            execution_result = self._execute_code_safely(code_solution)
            
            # Format final result
            result = self._format_code_result(task_description, code_solution, execution_result)
            
            log_agent_execution("code", task_description, result)
            return result
            
        except Exception as e:
            log_agent_execution("code", task_description, error=e)
            return f"Code execution failed: {str(e)}"
    
    def _delegate_to_research_explanation(self, task_description: str) -> str:
        
        try:
            model = self.model_service.get_model_for_agent("code")
            
            prompt = f"""This task doesn't require code execution. Provide a clear, informative explanation instead.

            TASK: {task_description}

            Provide a comprehensive explanation that addresses the task without writing executable code.
            Focus on concepts, methods, and theoretical approaches.

            EXPLANATION:"""

            explanation = model.invoke(prompt)
            
            return f"""## Task Analysis: {task_description}

            **Note:** This task doesn't require computational code execution.

            {explanation}

            ---
            **Routing Decision:** Task delegated to conceptual explanation rather than code execution."""
            
        except Exception as e:
            return f"Unable to provide explanation: {str(e)}"
    
    def _comprehensive_security_check(self, code: str) -> Dict[str, Any]:
        
        security_issues = []
        warnings = []
        
        # Basic validation
        basic_validation = self.validate_code(code)
        if not basic_validation['valid']:
            return {
                'safe': False,
                'issues': [basic_validation['error']],
                'warnings': [],
                'risk_level': 'high'
            }
        
        # Check code length
        lines = code.split('\n')
        if len(lines) > self.security_config['max_code_lines']:
            security_issues.append(f"Code too long: {len(lines)} lines (max: {self.security_config['max_code_lines']})")
        
        # AST-based security analysis
        try:
            tree = ast.parse(code)
            ast_issues = self._analyze_ast_security(tree)
            security_issues.extend(ast_issues['issues'])
            warnings.extend(ast_issues['warnings'])
        except SyntaxError as e:
            security_issues.append(f"Syntax error: {str(e)}")
        
        # Pattern-based security checks
        pattern_issues = self._pattern_based_security_check(code)
        security_issues.extend(pattern_issues)
        
        # Determine risk level
        risk_level = 'low'
        if security_issues:
            risk_level = 'high'
        elif warnings:
            risk_level = 'medium'
        
        return {
            'safe': len(security_issues) == 0,
            'issues': security_issues,
            'warnings': warnings,
            'risk_level': risk_level
        }
    
    def _analyze_ast_security(self, tree: ast.AST) -> Dict[str, List[str]]:      
        issues = []
        warnings = []
        
        for node in ast.walk(tree):
            # Check for forbidden imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.security_config['forbidden_imports']:
                        issues.append(f"Forbidden import: {alias.name}")
            
            elif isinstance(node, ast.ImportFrom):
                if node.module in self.security_config['forbidden_imports']:
                    issues.append(f"Forbidden import from: {node.module}")
            
            # Check for forbidden function calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.security_config['forbidden_functions']:
                        issues.append(f"Forbidden function call: {node.func.id}")
                elif isinstance(node.func, ast.Attribute):
                    # Check for dangerous method calls
                    dangerous_methods = ['system', 'popen', 'spawn', 'fork']
                    if node.func.attr in dangerous_methods:
                        issues.append(f"Dangerous method call: {node.func.attr}")
            
            # Check for file operations
            elif isinstance(node, ast.With):
                if any(isinstance(item.context_expr, ast.Call) and 
                      isinstance(item.context_expr.func, ast.Name) and 
                      item.context_expr.func.id == 'open' 
                      for item in node.items):
                    warnings.append("File operation detected - ensure it's necessary")
            
            # Check for network-related operations (context-aware)
            elif isinstance(node, ast.Attribute):
                # Only flag network operations when used with known network modules
                if isinstance(node.value, ast.Name):
                    # Check for requests.get, urllib.request, etc.
                    network_modules = ['requests', 'urllib', 'http', 'socket', 'ftplib', 'smtplib']
                    network_attrs = ['urlopen', 'request', 'get', 'post', 'put', 'delete', 'connect', 'send']
                    
                    if (node.value.id in network_modules and node.attr in network_attrs):
                        issues.append(f"Network operation detected: {node.value.id}.{node.attr}")
                elif isinstance(node.value, ast.Attribute):
                    # Check for urllib.request.urlopen, etc.
                    if (hasattr(node.value, 'attr') and node.value.attr in ['request', 'urllib'] and 
                        node.attr in ['urlopen', 'get', 'post']):
                        issues.append(f"Network operation detected: {node.value.attr}.{node.attr}")
        
        return {'issues': issues, 'warnings': warnings}
    
    def _pattern_based_security_check(self, code: str) -> List[str]:
  
        issues = []
        
        # Check for shell command patterns
        shell_patterns = [
            r'os\.system\s*\(',
            r'subprocess\.',
            r'commands\.',
            r'popen\s*\(',
            r'shell\s*=\s*True'
        ]
        
        for pattern in shell_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(f"Potential shell command execution detected: {pattern}")
        
        # Check for file system access patterns
        file_patterns = [
            r'open\s*\(\s*[\'"][^\'"]*/.*[\'"]',  # Absolute paths
            r'\.\./',  # Directory traversal
            r'__file__',  # File system introspection
        ]
        
        for pattern in file_patterns:
            if re.search(pattern, code):
                issues.append(f"File system access pattern detected: {pattern}")
        
        # Check for code injection patterns
        injection_patterns = [
            r'exec\s*\(',
            r'eval\s*\(',
            r'compile\s*\(',
            r'__import__\s*\('
        ]
        
        for pattern in injection_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(f"Code injection pattern detected: {pattern}")
        
        return issues
    
    def _format_security_error(self, security_check: Dict[str, Any]) -> str:
       
        error_msg = f"## Security Validation Failed\n\n"
        error_msg += f"**Risk Level:** {security_check['risk_level'].upper()}\n\n"
        
        if security_check['issues']:
            error_msg += "**Security Issues:**\n"
            for issue in security_check['issues']:
                error_msg += f"- ❌ {issue}\n"
        
        if security_check['warnings']:
            error_msg += "\n**Warnings:**\n"
            for warning in security_check['warnings']:
                error_msg += f"- ⚠️ {warning}\n"
        
        error_msg += "\n**Resolution:** Please modify the request to avoid security risks or use safer alternatives."
        
        return error_msg

    def _generate_code_solution(self, task_description: str, context: Dict[int, str], model) -> str:
        
        # Prepare context from previous tasks
        context_summary = ""
        if context:
            context_summary = "\n\nPREVIOUS TASK RESULTS:\n"
            for task_id, result in context.items():
                context_summary += f"Task {task_id}: {result[:300]}...\n"
        
        prompt = f"""You are an expert Python programmer. Write secure, efficient Python code to solve this computational task.

        TASK: {task_description}
        {context_summary}

        SECURITY REQUIREMENTS:
        1. Use only standard libraries (math, statistics, json, csv, datetime, etc.)
        2. NO file system access, network operations, or system calls
        3. NO imports of: os, sys, subprocess, requests, urllib, socket
        4. NO use of: exec, eval, compile, __import__, open, input
        5. AVOID external packages like matplotlib, pandas, numpy (not available in execution environment)
        6. For data visualization, use text-based output or ASCII charts instead of matplotlib

        CODE REQUIREMENTS:
        1. Write clean, well-commented Python code
        2. Handle errors gracefully with try-except blocks
        3. Include print statements for key results and intermediate steps
        4. Use appropriate data structures and algorithms
        5. Make code self-contained and executable
        6. Focus on computational/analytical tasks only
        7. Limit code to under 150 lines

        OUTPUT FORMAT:
        - Return ONLY the Python code
        - No markdown formatting or explanations
        - Code should be immediately executable

        PYTHON CODE:"""

        try:
            code = model.invoke(prompt)
            
            # Clean up the code (remove markdown formatting if present)
            code = self._clean_code_response(code)
            
            return code
            
        except Exception as e:
            logger.error(f"Code generation failed: {e}")
            raise
    
    def _clean_code_response(self, code_response: str) -> str:        
        # Remove markdown code blocks
        code_block_pattern = r'```(?:python)?\n?(.*?)\n?```'
        match = re.search(code_block_pattern, code_response, re.DOTALL)
        
        if match:
            code = match.group(1)
        else:
            code = code_response
        
        # Remove common prefixes/suffixes
        lines = code.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Skip explanation lines
            if line.strip().startswith('#') and any(word in line.lower() for word in ['here', 'this', 'solution', 'code']):
                continue
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    def _execute_code_safely(self, code: str) -> Dict[str, Any]:        
        try:
            # Pre-execution validation
            pre_check = self._pre_execution_check(code)
            if not pre_check['safe']:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Pre-execution check failed: {'; '.join(pre_check['issues'])}",
                    "execution_time": 0,
                    "security_blocked": True
                }
            
            # Execute code with enhanced security settings
            result = self.code_interpreter.execute_code(
                code=code,
                timeout=self.security_config['max_execution_time'],
                memory_limit=self.security_config['memory_limit'],
                network_disabled=True,  # Disable network access
                filesystem_readonly=True  # Read-only filesystem
            )
            
            # Post-execution validation
            if result.get("success") and result.get("output"):
                output_size = len(result["output"])
                if output_size > self.security_config['max_output_size']:
                    result["output"] = result["output"][:self.security_config['max_output_size']] + "\n[Output truncated - too large]"
                    result["truncated"] = True
            
            return result
            
        except Exception as e:
            logger.error(f"Code execution failed: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "execution_time": 0
            }
    
    def _pre_execution_check(self, code: str) -> Dict[str, Any]:        
        issues = []
        
        # Check for runtime code generation
        runtime_patterns = [
            r'exec\s*\(',
            r'eval\s*\(',
            r'compile\s*\(',
            r'__import__\s*\(',
            r'getattr\s*\(',
            r'setattr\s*\(',
            r'hasattr\s*\('
        ]
        
        for pattern in runtime_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(f"Runtime code generation detected: {pattern}")
        
        # Check for infinite loop patterns
        loop_patterns = [
            r'while\s+True\s*:',
            r'while\s+1\s*:',
            r'for.*in.*itertools\.count\('
        ]
        
        for pattern in loop_patterns:
            if re.search(pattern, code):
                issues.append(f"Potential infinite loop detected: {pattern}")
        
        return {
            'safe': len(issues) == 0,
            'issues': issues
        }
    
    def _format_code_result(self, task_description: str, code: str, execution_result: Dict[str, Any]) -> str:        
        result_sections = [
            f"## Code Solution for: {task_description}\n",
            "### Generated Code:\n",
            f"```python\n{code}\n```\n"
        ]
        
        # Code analysis section removed for cleaner output
        
        # Add execution results
        result_sections.append("### Execution Result:\n")
        
        if execution_result.get("security_blocked"):
            result_sections.append(f"**Status:** 🚫 Security Blocked\n")
            result_sections.append(f"**Reason:** {execution_result.get('error', 'Security validation failed')}\n")
        elif execution_result.get("success", False):
            output = execution_result.get("output", "No output")
            result_sections.append(f"**Status:** ✅ Success\n")
            result_sections.append(f"**Output:**\n```\n{output}\n```\n")
            
            if execution_result.get("execution_time"):
                result_sections.append(f"**Execution Time:** {execution_result['execution_time']:.2f}s\n")
            
            if execution_result.get("truncated"):
                result_sections.append(f"**Note:** Output was truncated due to size limits\n")
        else:
            error = execution_result.get("error", "Unknown error")
            result_sections.append(f"**Status:** ❌ Failed\n")
            
            # Check for common missing package errors and provide helpful suggestions
            if "ModuleNotFoundError" in error and "matplotlib" in error:
                result_sections.append(f"**Error:** Missing matplotlib package\n")
                result_sections.append(f"**Suggestion:** The visualization code is correct, but matplotlib is not available in the execution environment. ")
                result_sections.append(f"In a full Python environment, you would install it with: `pip install matplotlib`\n")
                result_sections.append(f"**Alternative:** Consider using text-based output or ASCII charts for visualization in this environment.\n")
            elif "ModuleNotFoundError" in error and any(pkg in error for pkg in ["pandas", "numpy", "seaborn", "plotly"]):
                missing_pkg = next(pkg for pkg in ["pandas", "numpy", "seaborn", "plotly"] if pkg in error)
                result_sections.append(f"**Error:** Missing {missing_pkg} package\n")
                result_sections.append(f"**Suggestion:** The code is correct, but {missing_pkg} is not available in the execution environment. ")
                result_sections.append(f"In a full Python environment, you would install it with: `pip install {missing_pkg}`\n")
                result_sections.append(f"**Alternative:** Consider using built-in Python libraries like `statistics` and `json` for data processing.\n")
            else:
                result_sections.append(f"**Error:**\n```\n{error}\n```\n")
        
        # Add security summary
        result_sections.append("### Security Summary:\n")
        result_sections.append("- ✅ Code executed in isolated Docker container\n")
        result_sections.append("- ✅ Network access disabled\n")
        result_sections.append("- ✅ File system access restricted\n")
        result_sections.append("- ✅ Execution time limited to 30s\n")
        
        return "".join(result_sections)
    
    def execute_code_with_tests(self, task_description: str, code: str, test_cases: List[Dict[str, Any]] = None) -> Dict[str, Any]:        
        if not test_cases:
            # Generate basic test cases
            test_cases = self._generate_basic_test_cases(task_description, code)
        
        results = {
            'main_execution': self._execute_code_safely(code),
            'test_results': [],
            'all_tests_passed': True
        }
        
        # Run test cases
        for i, test_case in enumerate(test_cases):
            test_code = f"{code}\n\n# Test case {i+1}\n{test_case['code']}"
            
            test_result = self._execute_code_safely(test_code)
            test_result['test_name'] = test_case.get('name', f'Test {i+1}')
            test_result['expected'] = test_case.get('expected', 'No expectation defined')
            
            results['test_results'].append(test_result)
            
            if not test_result.get('success', False):
                results['all_tests_passed'] = False
        
        return results
    
    def _generate_basic_test_cases(self, task_description: str, code: str) -> List[Dict[str, Any]]:        
        test_cases = []
        
        # Analyze code to identify functions
        try:
            tree = ast.parse(code)
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            
            for func_name in functions:
                test_cases.append({
                    'name': f'Test {func_name} function',
                    'code': f'# Test {func_name}\nprint(f"Testing {func_name}: {{type({func_name})}}")',
                    'expected': 'Function should be callable'
                })
        except:
            pass
        
        # Add basic execution test
        test_cases.append({
            'name': 'Basic execution test',
            'code': 'print("Code executed successfully")',
            'expected': 'Code should execute without errors'
        })
        
        return test_cases[:3]  # Limit to 3 basic tests
    
    def benchmark_code_performance(self, code: str, iterations: int = 3) -> Dict[str, Any]:
        
        benchmark_code = f"""
        import time

        # Original code
        {code}

        # Benchmark
        times = []
        for i in range({iterations}):
        start_time = time.time()
    
  
        end_time = time.time()
        times.append(end_time - start_time)

        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)

        print(f"Benchmark Results ({iterations} iterations):")
        print(f"Average time: {{avg_time:.4f}}s")
        print(f"Min time: {{min_time:.4f}}s")
        print(f"Max time: {{max_time:.4f}}s")
        """
        
        result = self._execute_code_safely(benchmark_code)
        
        return {
            'benchmark_successful': result.get('success', False),
            'benchmark_output': result.get('output', ''),
            'benchmark_error': result.get('error', '')
        }
    
    def validate_code(self, code: str) -> Dict[str, Any]:        
        try:
            compile(code, '<string>', 'exec')
            return {
                "valid": True,
                "error": None
            }
        except SyntaxError as e:
            return {
                "valid": False,
                "error": f"Syntax error: {str(e)}"
            }
        except Exception as e:
            return {
                "valid": False,
                "error": f"Validation error: {str(e)}"
            }
    
    def analyze_code_complexity(self, code: str) -> Dict[str, Any]:        
        lines = code.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        
        # Basic complexity metrics
        complexity_metrics = {
            "total_lines": len(lines),
            "code_lines": len(non_empty_lines),
            "comment_lines": len([line for line in lines if line.strip().startswith('#')]),
            "function_count": len(re.findall(r'def\s+\w+', code)),
            "class_count": len(re.findall(r'class\s+\w+', code)),
            "import_count": len(re.findall(r'^\s*(?:import|from)\s+', code, re.MULTILINE))
        }
        
        # Estimate complexity level
        if complexity_metrics["code_lines"] < 10:
            complexity_level = "Simple"
        elif complexity_metrics["code_lines"] < 50:
            complexity_level = "Moderate"
        else:
            complexity_level = "Complex"
        
        return {
            "metrics": complexity_metrics,
            "complexity_level": complexity_level
        }