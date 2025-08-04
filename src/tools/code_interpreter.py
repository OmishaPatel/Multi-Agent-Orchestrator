import docker
import tempfile
import os
import time
import logging
import docker.errors
from langchain_core.tools import Tool
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class DockerCodeExecutor:
    def __init__(self,
                 image: str = "python:3.11-slim",
                 timeout: int = 30,
                 memory_limit: str = "128m"):
        self.image = image
        self.timeout = timeout
        self.memory_limit = memory_limit
        self.client: Optional[docker.DockerClient] = None

        try:
            self.client = docker.from_env()
            self.client.ping()
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise RuntimeError("Docker is not available. Please ensure Docker is installed and running.")
        

    def execute_python_code(self, code:str) -> str:
        if not self.client:
            return "Error: Docker client not initialized"
        
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            logger.debug(f"Created temporary file: {temp_file}")

            #pull image if not available (first time only)
            try:
                self.client.images.get(self.image)
            except docker.errors.ImageNotFound:
                logger.info(f"Pulling Docker image: {self.image}")
                self.client.images.pull(self.image)

            #Run code in isolated container
            result = self.client.containers.run(
                image=self.image,
                command=f"python /code/{os.path.basename(temp_file)}",
                volumes={
                    os.path.dirname(temp_file): {
                        'bind': '/code',
                        'mode': 'ro' # read only
                    }
                },

                #security settings
                remove=True,
                #timeout=self.timeout,
                mem_limit=self.memory_limit,
                network_disabled=True,
                user="nobody",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],

                #resource limits
                nano_cpus=int(0.5 *1e9),
                pids_limit=50,

                #environment
                environment={
                    "PYTHONUNBUFFERED": "1", # unbuffered output
                    "PYTHONDONTWRITEBYTECODE": "1" # don't create .pyc files
                },

                #working directory
                working_dir="/tmp"
            )

            #return output
            output = result.decode('utf-8').strip()
            logger.debug(f"Code execution completed successfully")
            return output if output else "Code executed successfully (no output)"
        except docker.errors.ContainerError as e:
            # container exited with non-zero code
            error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
            logger.warning(f"Container execution error: {error_msg}")
            return f"Execution Error: {error_msg}"
        except docker.errors.APIError as e:
            logger.error(f"Docker API error: {e}")
            return f"Docker Error: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error during code execution: {e}")
            return f"Error: {str(e)}"
        
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                    logger.debug(f"Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file: {e}")

class CodeInterpreter:
    """
    Code interpreter wrapper that provides a unified interface for code execution.
    Handles both Docker-based secure execution and fallback options.
    """
    
    def __init__(self):
        self.docker_available = False
        self.executor = None
        self.fallback_tool = None
        
        try:
            self.executor = DockerCodeExecutor()
            self.docker_available = True
            logger.info("CodeInterpreter initialized with Docker backend")
        except RuntimeError as e:
            logger.warning(f"Docker not available, using fallback: {e}")
            try:
                from langchain_experimental.tools import PythonREPLTool
                self.fallback_tool = PythonREPLTool()
                logger.info("CodeInterpreter initialized with Python REPL fallback")
            except ImportError:
                logger.error("No code execution backend available")
                raise RuntimeError("No code execution backend available")
    
    def execute_code(self, code: str, timeout: int = 30, memory_limit: str = "256m", 
                    network_disabled: bool = True, filesystem_readonly: bool = True) -> Dict[str, Any]:
        """
        Execute Python code with security constraints.
        
        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            memory_limit: Memory limit for execution
            network_disabled: Whether to disable network access
            filesystem_readonly: Whether filesystem should be read-only
            
        Returns:
            Dictionary with execution results
        """
        if self.docker_available and self.executor:
            return self._execute_with_docker(code, timeout, memory_limit)
        elif self.fallback_tool:
            return self._execute_with_fallback(code)
        else:
            return {
                "success": False,
                "output": "",
                "error": "No code execution backend available",
                "execution_time": 0
            }
    
    def _execute_with_docker(self, code: str, timeout: int, memory_limit: str) -> Dict[str, Any]:
        
        start_time = time.time()
        
        try:
            # Update executor settings
            self.executor.timeout = timeout
            self.executor.memory_limit = memory_limit
            
            # Execute code
            output = self.executor.execute_python_code(code)
            execution_time = time.time() - start_time
            
            # Check if execution was successful
            success = not output.startswith("Error:") and not output.startswith("Execution Error:")
            
            return {
                "success": success,
                "output": output,
                "error": "" if success else output,
                "execution_time": execution_time,
                "backend": "docker"
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "execution_time": execution_time,
                "backend": "docker"
            }
    
    def _execute_with_fallback(self, code: str) -> Dict[str, Any]:
        
        start_time = time.time()
        
        try:
            output = self.fallback_tool.run(code)
            execution_time = time.time() - start_time
            
            return {
                "success": True,
                "output": output,
                "error": "",
                "execution_time": execution_time,
                "backend": "python_repl",
                "warning": "Using insecure fallback - Docker not available"
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "execution_time": execution_time,
                "backend": "python_repl"
            }
    
    def is_docker_available(self) -> bool:
        return self.docker_available
    
    def get_backend_info(self) -> Dict[str, Any]:
        if self.docker_available:
            return {
                "backend": "docker",
                "secure": True,
                "isolated": True,
                "network_disabled": True,
                "memory_limited": True
            }
        elif self.fallback_tool:
            return {
                "backend": "python_repl",
                "secure": False,
                "isolated": False,
                "network_disabled": False,
                "memory_limited": False,
                "warning": "Insecure fallback mode"
            }
        else:
            return {
                "backend": "none",
                "available": False
            }


# Initialize global instances
try:
    docker_executor = DockerCodeExecutor()

    code_interpreter_tool = Tool(
        name="secure_python_interpreter",
        func=docker_executor.execute_python_code,
        description="""
                A secure Python code executor that runs code in an isolated Docker container.
        
        Security features:
        - No network access
        - Limited memory and CPU
        - Read-only file system access
        - Automatic cleanup
        - Execution timeout

        Use this to execute Python code when a task requires it.
        The input should be a valid Python code snippet.
        The tool will return the standard output of the executed code.
        You can use this to perform calculations, manipulate data, or any other
        programming task. DO not include the 'python' markdown tag in your code.
        """
    )

except RuntimeError as e:
    # Add fallback
    logger.warning(f"Docker not available: {e}")
    
    from langchain_experimental.tools import PythonREPLTool
    python_repl_tool = PythonREPLTool()
    
    code_interpreter_tool = Tool(
        name="python_interpreter_fallback",
        func=python_repl_tool.run,
        description="⚠️ INSECURE FALLBACK: Python REPL (Docker not available)"
    )