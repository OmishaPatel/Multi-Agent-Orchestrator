# src/core/model_service.py
import logging
from typing import Dict, Any, Optional
from .model_router import EnvironmentAwareModelRouter
from .model_fallback import ModelFallbackChain
from ..config.ollama_config import OllamaModelManager

logger = logging.getLogger(__name__)

class ModelService:
    """
    High-level service that integrates model routing and fallback capabilities.
    This is the main interface that agents should use for model interactions.
    """
    
    def __init__(self):
        self.router = EnvironmentAwareModelRouter()
        self.fallback_chain = ModelFallbackChain(self.router)
        self.ollama_manager = OllamaModelManager()
        
    async def generate_response(
        self,
        prompt: str,
        agent_type: str = "general",
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        
        async def model_executor(model: str, task_description: str) -> str:
            if self.router.env_config.environment.value == "development":
                # Use Ollama for development
                return await self.ollama_manager.generate_response(task_description, model)
            else:
                # Use appropriate provider for testing/production
                # This would integrate with cloud/self-hosted model providers
                return await self._execute_cloud_model(model, task_description)
        
        return await self.fallback_chain.execute_with_fallback(
            prompt, agent_type, model_executor, context
        )
    
    async def _execute_cloud_model(self, model: str, prompt: str) -> str:
        """
        Execute model call for cloud/production environments.
        This would integrate with actual model providers.
        """
        # Placeholder for cloud model integration
        # In real implementation, this would call HuggingFace, vLLM, etc.
        logger.info(f"Executing {model} in cloud environment")
        return f"Response from {model}: {prompt[:50]}..."
    
    async def get_system_status(self) -> Dict[str, Any]:
        return {
            "router_status": {
                "environment": self.router.env_config.environment.value,
                "model_metrics": self.router.model_metrics
            },
            "fallback_status": self.fallback_chain.get_fallback_status(),
            "resource_status": await self.router.get_system_resources()
        }
