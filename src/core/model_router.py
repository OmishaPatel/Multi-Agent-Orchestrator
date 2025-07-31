import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass
import time
import psutil

from ..config.model_environment import Environment, EnvironmentAwareModelConfig
from ..config.ollama_config import OllamaModelManager


logger = logging.getLogger(__name__)

class TaskComplexity(Enum):
    SIMPLE = "simple" # basic text processing, simple Q & A
    MODERATE = "moderate" # code generation, research tasks
    COMPLEX = "complex" # multi-step reasoning
    CRITICAL = "critical" # critical tasks requiring highest accuracy


class ModelCapability(Enum):
    MINIMAL = "minimal" # 0.5B -1B parameters
    BASIC = "basic" # 1B -3B parameter
    STANDARD = "standard" #3b - 7b parameter
    ADVANCED = "advanced" # 7b+

@dataclass
class ModelMetrics:
    response_time: float
    success_rate: float
    error_count: int
    last_used: float
    total_requests: int

@dataclass
class ModelFallbackConfig:
    primary_model: str
    fallback_models: List[str]
    max_retries: int = 3
    retry_delay: float = 1.0
    health_check_interval: int = 300 # 5 minutes


class EnvironmentAwareModelRouter:
    """
    Intelligent model router that selects optimal models based on:
    - Current environment (dev/test/prod)
    - Task complexity assessment
    - Resource availability
    - Model health and performance metrics
    - Fallback chain management
    """

    def __init__(self):
        self.env_config = EnvironmentAwareModelConfig()
        self.ollama_manager = OllamaModelManager()

        self.model_metrics: Dict[str, ModelMetrics] = {}
        self.fallback_configs = self._initialize_fallback_configs()

        self.complexity_mapping = {
            TaskComplexity.SIMPLE: ModelCapability.MINIMAL,
            TaskComplexity.MODERATE: ModelCapability.BASIC,
            TaskComplexity.COMPLEX: ModelCapability.STANDARD,
            TaskComplexity.CRITICAL: ModelCapability.ADVANCED
        }

        logger.info(f"Model router initialized for {self.env_config.environment.value} environment")

    async def get_system_resources(self) -> Dict[str, float]:
        try:
            memory = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.1)
            return {
                "total_ram_gb": memory.total / (1024**3),
                "available_ram_gb": memory.available / (1024**3),
                "used_ram_gb": memory.used / (1024**3),
                "ram_percent": memory.percent,
                "cpu_percent": cpu
            }

        except Exception as e:
            logger.warning(f"Failed to get system resources: {e}")
            return {
                "total_ram_gb": 8.0,
                "available_ram_gb": 4.0,
                "used_ram_gb": 4.0,
                "ram_percent": 50.0,
                "cpu_percent": 50.0
            }

    def _initialize_fallback_configs(self) -> Dict[Environment, ModelFallbackConfig]:
        configs = {}

        if self.env_config.environment == Environment.DEVELOPMENT:
            configs[Environment.DEVELOPMENT] = ModelFallbackConfig(
                primary_model="phi3:mini",
                fallback_models=["llama3.2:1b", "qwen2:0.5b"],
                max_retries=2,
                retry_delay=0.5,
            )

        elif self.env_config.environment == Environment.TESTING:
            configs[Environment.TESTING] = ModelFallbackConfig(
                primary_model="gpt-3.5-turbo",
                fallback_models=["gpt-4o-mini"],
                max_retries=3,
                retry_delay=1.0
            )

        else:
            configs[Environment.PRODUCTION] = ModelFallbackConfig(
                primary_model="llama3.1:8b",
                fallback_models=["mistral:7b", "codellama:7b", "phi3:mini"]
            )

        return configs

    async def assess_task_complexity(self, task_description: str, context: Dict[str, Any] = None) -> TaskComplexity:
        """
        This is a simplified heuristic-based approach. Might consider dedicated classifier model in future.
        """
        task_lower = task_description.lower()
        context = context or {}

        critical_keywords = ["production", "critical", "security", "financial", "legal"]

        if any(keyword in task_lower for keyword in critical_keywords):
            return TaskComplexity.CRITICAL

        complex_keywords = [
            "analyze", "research", "multi-step", "reasoning", "complex", "architecture", "design", "optimization", "algorithm"
        ]

        if any(keyword in task_lower for keyword in complex_keywords):
            return TaskComplexity.COMPLEX

        moderate_keywords = [
            "code", "generate", "implement", "create", "build",
            "explain", "summarize", "translate"
        ]

        if any(keyword in task_lower for keyword in moderate_keywords):
            return TaskComplexity.MODERATE

        if context.get("required_reasoning", False):
            return TaskComplexity.COMPLEX
        if context.get("code_generation", False):
            return TaskComplexity.MODERATE

        return TaskComplexity.MODERATE

    async def select_optimal_model(
        self,
        task_description: str,
        agent_type: str = "general",
        context: Dict[str, Any] = None
    ) -> str:
        complexity = await self.assess_task_complexity(task_description, context)
        logger.info(f"Task complexity assessed as: {complexity.value}")

        env_models = self.env_config.config["models"]
        base_model = env_models.get(agent_type, env_models.get("planning", "phi3:mini"))

        if self.env_config.environment == Environment.DEVELOPMENT:
            return await self._select_development_model(complexity, base_model)

        return await self._select_production_model(complexity, base_model, agent_type)

    async def _select_development_model(self, complexity: TaskComplexity, base_model: str) -> str:
        resources = await self.get_system_resources()
        available_ram = resources.get("available_ram_gb", 4.0)
        
        # Use similar logic as OllamaModelManager for consistency
        if complexity == TaskComplexity.SIMPLE and available_ram < 2.0:
            return "qwen2:0.5b"  # Minimal resource usage
        elif complexity in [TaskComplexity.SIMPLE, TaskComplexity.MODERATE] and available_ram < 4.0:
            return "llama3.2:1b"  # Lightweight but capable
        else:
            return base_model  # Use configured model (phi3:mini)

    async def _select_production_model(
        self, 
        complexity: TaskComplexity, 
        base_model: str, 
        agent_type: str
    ) -> str:
        env_models = self.env_config.config["models"]
        
        # Map complexity to model selection
        if complexity == TaskComplexity.CRITICAL:
            # Use the most capable model available
            if "advanced" in env_models:
                return env_models["advanced"]
            return base_model
            
        elif complexity == TaskComplexity.COMPLEX:
            # Use research or code model if available for complex tasks
            if agent_type == "research" and "research" in env_models:
                return env_models["research"]
            elif agent_type == "code" and "code" in env_models:
                return env_models["code"]
            return base_model
            
        else:
            # Use base model for simple/moderate tasks
            return base_model

    def _update_model_metrics(self, model: str, response_time: float, success: bool):
        if model not in self.model_metrics:
            self.model_metrics[model] = ModelMetrics(
                response_time=response_time,
                success_rate=1.0 if success else 0.0,
                error_count=0 if success else 1,
                last_used=time.time(),
                total_requests=1
            )
        else:
            metrics = self.model_metrics[model]
            metrics.total_requests += 1
            metrics.last_used = time.time()
            
            # Update success rate (exponential moving average)
            alpha = 0.1
            metrics.success_rate = (1 - alpha) * metrics.success_rate + alpha * (1.0 if success else 0.0)
            
            # Update response time (exponential moving average)
            metrics.response_time = (1 - alpha) * metrics.response_time + alpha * response_time
            
            if not success:
                metrics.error_count += 1
    async def route_request(
        self, 
        task_description: str, 
        agent_type: str = "general",
        context: Dict[str, Any] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Route a request to the optimal model with fallback handling.
        
        Returns:
            Tuple of (selected_model, routing_metadata)
        """
        start_time = time.time()
        
        try:
            # Select optimal model
            selected_model = await self.select_optimal_model(task_description, agent_type, context)
            
            # Get fallback configuration
            fallback_config = self.fallback_configs.get(self.env_config.environment)
            
            routing_metadata = {
                "selected_model": selected_model,
                "environment": self.env_config.environment.value,
                "agent_type": agent_type,
                "fallback_available": fallback_config is not None,
                "selection_time": time.time() - start_time
            }
            
            logger.info(f"Routed {agent_type} request to {selected_model}")
            return selected_model, routing_metadata
            
        except Exception as e:
            logger.error(f"Error in model routing: {e}")
            # Emergency fallback
            fallback_model = "phi3:mini"  # Safe default
            routing_metadata = {
                "selected_model": fallback_model,
                "environment": self.env_config.environment.value,
                "agent_type": agent_type,
                "fallback_used": True,
                "error": str(e),
                "selection_time": time.time() - start_time
            }
            return fallback_model, routing_metadata

    def get_model_health_status(self) -> Dict[str, Dict[str, Any]]:
        health_status = {}
        current_time = time.time()
        
        for model, metrics in self.model_metrics.items():
            # Consider model unhealthy if success rate < 80% or too many recent errors
            is_healthy = (
                metrics.success_rate >= 0.8 and
                metrics.error_count < 10 and
                (current_time - metrics.last_used) < 3600  # Used within last hour
            )
            
            health_status[model] = {
                "healthy": is_healthy,
                "success_rate": metrics.success_rate,
                "avg_response_time": metrics.response_time,
                "error_count": metrics.error_count,
                "last_used": metrics.last_used,
                "total_requests": metrics.total_requests
            }
            
        return health_status