import asyncio
import logging
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass
import time

from .model_router import EnvironmentAwareModelRouter, ModelFallbackConfig

logger = logging.getLogger(__name__)

@dataclass
class FallbackAttempt:
    model: str
    attempt_number: int
    start_time: float
    end_time: Optional[float] = None
    success: bool = False
    error: Optional[str] = None
    response: Optional[str] = None

class ModelFallbackChain:
    """
    Manages fallback chain execution with retry logic and health monitoring.
    
    Key features:
    - Automatic fallback to secondary models on failure
    - Configurable retry delays and max attempts
    - Circuit breaker pattern for unhealthy models
    - Detailed logging and metrics collection
    """
    
    def __init__(self, router: EnvironmentAwareModelRouter):
        self.router = router
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}
        
    async def execute_with_fallback(
        self,
        task_description: str,
        agent_type: str,
        model_executor: Callable[[str, str], Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute a task with automatic fallback handling.
        
        Args:
            task_description: Description of the task to execute
            agent_type: Type of agent (planning, research, code)
            model_executor: Async function that executes the task with a given model
            context: Additional context for model selection
            
        Returns:
            Dict containing response, metadata, and fallback information
        """
        # Get primary model and fallback configuration
        primary_model, routing_metadata = await self.router.route_request(
            task_description, agent_type, context
        )
        
        fallback_config = self.router.fallback_configs.get(self.router.env_config.environment)
        if not fallback_config:
            # No fallback configured, execute with primary model only
            return await self._execute_single_model(
                primary_model, task_description, model_executor, routing_metadata
            )
        
        # Build fallback chain
        fallback_chain = [primary_model] + fallback_config.fallback_models
        fallback_attempts: List[FallbackAttempt] = []
        
        # Execute with fallback chain
        for attempt_num, model in enumerate(fallback_chain):
            if self._is_circuit_breaker_open(model):
                logger.warning(f"Circuit breaker open for {model}, skipping")
                continue
                
            attempt = FallbackAttempt(
                model=model,
                attempt_number=attempt_num,
                start_time=time.time()
            )
            
            try:
                logger.info(f"Attempting execution with {model} (attempt {attempt_num + 1})")
                
                # Execute with current model
                response = await model_executor(model, task_description)
                
                # Success!
                attempt.end_time = time.time()
                attempt.success = True
                attempt.response = response
                fallback_attempts.append(attempt)
                
                # Update router metrics
                execution_time = attempt.end_time - attempt.start_time
                self.router._update_model_metrics(model, execution_time, True)
                
                # Reset circuit breaker on success
                self._reset_circuit_breaker(model)
                
                return {
                    "response": response,
                    "model_used": model,
                    "primary_model": primary_model,
                    "fallback_used": attempt_num > 0,
                    "attempts": fallback_attempts,
                    "routing_metadata": routing_metadata,
                    "execution_time": execution_time
                }
                
            except Exception as e:
                attempt.end_time = time.time()
                attempt.error = str(e)
                fallback_attempts.append(attempt)
                
                execution_time = attempt.end_time - attempt.start_time
                self.router._update_model_metrics(model, execution_time, False)
                
                logger.warning(f"Model {model} failed: {e}")
                
                # Update circuit breaker
                self._record_failure(model)
                
                # If this was the last model in chain, raise the error
                if attempt_num == len(fallback_chain) - 1:
                    logger.error("All models in fallback chain failed")
                    raise Exception(f"All fallback models failed. Last error: {e}")
                
                # Wait before trying next model
                if attempt_num < len(fallback_chain) - 1:
                    await asyncio.sleep(fallback_config.retry_delay)
        
        raise Exception("Fallback chain execution failed unexpectedly")

    async def _execute_single_model(
        self,
        model: str,
        task_description: str,
        model_executor: Callable[[str, str], Any],
        routing_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        start_time = time.time()
        
        try:
            response = await model_executor(model, task_description)
            execution_time = time.time() - start_time
            
            self.router._update_model_metrics(model, execution_time, True)
            
            return {
                "response": response,
                "model_used": model,
                "primary_model": model,
                "fallback_used": False,
                "attempts": [FallbackAttempt(
                    model=model,
                    attempt_number=0,
                    start_time=start_time,
                    end_time=time.time(),
                    success=True,
                    response=response
                )],
                "routing_metadata": routing_metadata,
                "execution_time": execution_time
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.router._update_model_metrics(model, execution_time, False)
            raise

    def _is_circuit_breaker_open(self, model: str) -> bool:
        if model not in self.circuit_breakers:
            return False
            
        breaker = self.circuit_breakers[model]
        current_time = time.time()
        
        # Check if breaker should be reset (timeout expired)
        if current_time - breaker["last_failure"] > breaker["timeout"]:
            self._reset_circuit_breaker(model)
            return False
            
        return breaker["failure_count"] >= breaker["threshold"]

    def _record_failure(self, model: str):
        current_time = time.time()
        
        if model not in self.circuit_breakers:
            self.circuit_breakers[model] = {
                "failure_count": 1,
                "last_failure": current_time,
                "threshold": 5,  # Open after 5 failures
                "timeout": 300   # Reset after 5 minutes
            }
        else:
            breaker = self.circuit_breakers[model]
            breaker["failure_count"] += 1
            breaker["last_failure"] = current_time
            
            if breaker["failure_count"] >= breaker["threshold"]:
                logger.warning(f"Circuit breaker opened for {model} after {breaker['failure_count']} failures")

    def _reset_circuit_breaker(self, model: str):
        if model in self.circuit_breakers:
            self.circuit_breakers[model]["failure_count"] = 0
            logger.info(f"Circuit breaker reset for {model}")

    def get_fallback_status(self) -> Dict[str, Any]:
        return {
            "circuit_breakers": self.circuit_breakers,
            "model_health": self.router.get_model_health_status(),
            "environment": self.router.env_config.environment.value,
            "fallback_configs": {
                env.value: {
                    "primary_model": config.primary_model,
                    "fallback_models": config.fallback_models,
                    "max_retries": config.max_retries
                }
                for env, config in self.router.fallback_configs.items()
            }
        }
