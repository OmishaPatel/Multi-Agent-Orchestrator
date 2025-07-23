import logging
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

class ClarityLogger:
    
    _instance = None
    _configured = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._configured:
            self.setup_logging()
            self._configured = True
    
    def setup_logging(
        self, 
        log_level: Optional[str] = None,
        log_file: Optional[str] = None,
        environment: Optional[str] = None
    ):
        
        # Get configuration from environment or defaults
        environment = environment or os.getenv("ENVIRONMENT", "development")
        log_level = log_level or self._get_log_level_for_environment(environment)
        
        # Create logs directory
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Configure formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(name)-20s | %(levelname)-8s | %(filename)s:%(lineno)d | %(funcName)s() | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(simple_formatter if environment == "production" else detailed_formatter)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        
        # File handlers
        handlers = [console_handler]
        
        if log_file or environment != "development":
            # Main log file
            main_log_file = log_file or log_dir / f"clarity_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.FileHandler(main_log_file)
            file_handler.setFormatter(detailed_formatter)
            file_handler.setLevel(logging.DEBUG)
            handlers.append(file_handler)
            
            # Error log file
            error_log_file = log_dir / f"clarity_errors_{datetime.now().strftime('%Y%m%d')}.log"
            error_handler = logging.FileHandler(error_log_file)
            error_handler.setFormatter(detailed_formatter)
            error_handler.setLevel(logging.ERROR)
            handlers.append(error_handler)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Add new handlers
        for handler in handlers:
            root_logger.addHandler(handler)
        
        # Configure specific loggers
        self._configure_component_loggers(environment)
        
        # Log the configuration
        logger = logging.getLogger("clarity.logging")
        logger.info(f"Logging configured for environment: {environment}")
        logger.info(f"Log level: {log_level}")
        logger.info(f"Handlers: {len(handlers)} configured")
    
    def _get_log_level_for_environment(self, environment: str) -> str:
        levels = {
            "development": "DEBUG",
            "testing": "INFO", 
            "production": "WARNING"
        }
        return levels.get(environment, "INFO")
    
    def _configure_component_loggers(self, environment: str):
        
        # Get environment-specific log levels
        quiet_terminal = os.getenv("QUIET_TERMINAL", "true").lower() == "true"
        verbose_logging = os.getenv("VERBOSE_LOGGING", "false").lower() == "true"
        
        # Framework loggers - reduce noise significantly
        logging.getLogger("uvicorn").setLevel(logging.INFO)
        
        # Uvicorn access logs are very noisy - quiet them unless verbose mode
        if verbose_logging:
            logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        else:
            logging.getLogger("uvicorn.access").setLevel(logging.WARNING if environment == "production" else logging.ERROR)
        
        logging.getLogger("fastapi").setLevel(logging.INFO)
        
        # Third-party libraries that generate excessive noise
        noisy_libraries = {
            "apscheduler": logging.ERROR if quiet_terminal else logging.INFO,
            "apscheduler.scheduler": logging.ERROR if quiet_terminal else logging.INFO,
            "apscheduler.executors": logging.ERROR if quiet_terminal else logging.INFO,
            "apscheduler.executors.default": logging.ERROR if quiet_terminal else logging.INFO,
            "watchfiles": logging.ERROR if quiet_terminal else logging.WARNING,
            "watchfiles.main": logging.ERROR if quiet_terminal else logging.WARNING,
            "tzlocal": logging.ERROR if quiet_terminal else logging.WARNING,
        }
        
        # Apply quiet settings unless in verbose mode
        if verbose_logging:
            # In verbose mode, allow more detail but still reduce the noisiest ones
            for logger_name in noisy_libraries:
                logging.getLogger(logger_name).setLevel(logging.WARNING)
        else:
            # In quiet mode, suppress most third-party noise
            for logger_name, level in noisy_libraries.items():
                logging.getLogger(logger_name).setLevel(level)
        
        # LangChain/LangGraph loggers
        logging.getLogger("langchain").setLevel(logging.WARNING)
        logging.getLogger("langgraph").setLevel(logging.INFO)
        
        # HTTP clients
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        
        # Redis
        logging.getLogger("redis").setLevel(logging.WARNING)
        
        # Docker (if used)
        logging.getLogger("docker").setLevel(logging.WARNING)
        
        # Clarity.ai component loggers
        component_level = logging.DEBUG if environment == "development" else logging.INFO
        
        clarity_components = [
            "clarity.agents.planning",
            "clarity.agents.research", 
            "clarity.agents.code",
            "clarity.graph.workflow",
            "clarity.graph.state",
            "clarity.api.routes",
            "clarity.services",
            "clarity.tools"
        ]
        
        for component in clarity_components:
            logging.getLogger(component).setLevel(component_level)

# Singleton instance
_clarity_logger = ClarityLogger()

def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None, 
    environment: Optional[str] = None
) -> logging.Logger:
    """
    Set up logging configuration for the entire application.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
        environment: Environment (development, testing, production)
    
    Returns:
        Logger instance
    """
    _clarity_logger.setup_logging(log_level, log_file, environment)
    return logging.getLogger("clarity.main")

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific component.
    
    Args:
        name: Logger name (e.g., 'clarity.agents.planning')
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)

# Convenience functions for different components
def get_agent_logger(agent_type: str) -> logging.Logger:
    """Get logger for an agent."""
    return get_logger(f"clarity.agents.{agent_type}")

def get_api_logger(route: str = "main") -> logging.Logger:
    """Get logger for API routes."""
    return get_logger(f"clarity.api.{route}")

def get_service_logger(service: str) -> logging.Logger:
    """Get logger for services."""
    return get_logger(f"clarity.services.{service}")

def get_workflow_logger() -> logging.Logger:
    """Get logger for workflow operations."""
    return get_logger("clarity.graph.workflow")

def get_state_logger() -> logging.Logger:
    """Get logger for state management."""
    return get_logger("clarity.graph.state")

# Context manager for request logging
class RequestLogger:
    """Context manager for request-specific logging."""
    
    def __init__(self, request_id: str, logger: logging.Logger):
        self.request_id = request_id
        self.logger = logger
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.info(f"[{self.request_id}] Request started")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = datetime.now() - self.start_time
        if exc_type:
            self.logger.error(f"[{self.request_id}] Request failed after {duration.total_seconds():.2f}s: {exc_val}")
        else:
            self.logger.info(f"[{self.request_id}] Request completed in {duration.total_seconds():.2f}s")

# Example usage patterns
def log_agent_execution(agent_type: str, task_description: str, result: Any = None, error: Exception = None):
    """Log agent execution with consistent format."""
    logger = get_agent_logger(agent_type)
    
    if error:
        logger.error(f"Agent execution failed - Task: {task_description} - Error: {error}", exc_info=True)
    else:
        logger.info(f"Agent execution completed - Task: {task_description} - Result: {type(result).__name__}")

def log_state_transition(from_state: str, to_state: str, thread_id: str):
    """Log state transitions."""
    logger = get_state_logger()
    logger.info(f"State transition [{thread_id}]: {from_state} -> {to_state}")

def log_api_request(method: str, path: str, status_code: int, duration: float, thread_id: str = None):
    """Log API requests."""
    logger = get_api_logger()
    thread_info = f"[{thread_id}] " if thread_id else ""
    logger.info(f"{thread_info}{method} {path} - {status_code} - {duration:.2f}s")