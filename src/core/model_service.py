import logging
import os
from typing import Dict, Any, Optional
from src.core.llm_wrappers.llm_factory import LLMFactory, AgentType, ModelEnvironment
from src.core.llm_wrappers.base_llm import BaseLLMWrapper
from src.utils.logging_config import get_service_logger

logger = get_service_logger("model")

class ModelService:
    """
    High-level service that provides LLM access for agents.
    Integrates with the LLM factory for environment-aware model selection.
    """
    
    def __init__(self):
        env_str = os.getenv("ENVIRONMENT", "development").lower()
        try:
            self.environment = ModelEnvironment(env_str)
        except ValueError:
            self.environment = ModelEnvironment.DEVELOPMENT
            
        self._llm_cache: Dict[str, BaseLLMWrapper] = {}
        
        logger.info(f"ModelService initialized for {self.environment.value} environment")
    
    def get_model_for_agent(self, agent_type: str) -> BaseLLMWrapper:
        agent_type_map = {
            "planning": AgentType.PLANNING,
            "research": AgentType.RESEARCH,
            "code": AgentType.CODE
        }
        
        agent_enum = agent_type_map.get(agent_type, AgentType.PLANNING)
        cache_key = f"{self.environment.value}_{agent_enum.value}"
        
        # Return cached instance if available
        if cache_key in self._llm_cache:
            return self._llm_cache[cache_key]
        
        # Create new LLM instance
        try:
            llm = LLMFactory.create_llm(agent_enum, self.environment)
            self._llm_cache[cache_key] = llm
            
            logger.info(f"Created LLM for {agent_type} agent: {llm.model_name}")
            return llm
            
        except Exception as e:
            logger.error(f"Failed to create LLM for {agent_type}: {e}")
            # Fallback to planning agent LLM
            if agent_enum != AgentType.PLANNING:
                return self.get_model_for_agent("planning")
            raise
    
    def get_available_models(self) -> Dict[str, str]:
        return {
            agent_type.value: config["model"]
            for agent_type, config in LLMFactory.MODEL_CONFIGS[self.environment].items()
        }
    
    def get_model_metrics(self) -> Dict[str, Any]:
        metrics = {}
        
        for cache_key, llm in self._llm_cache.items():
            metrics[cache_key] = llm.get_metrics()
        
        return metrics
    
    def clear_model_cache(self):
        for llm in self._llm_cache.values():
            if hasattr(llm, 'clear_cache'):
                llm.clear_cache()
        
        self._llm_cache.clear()
        logger.info("Model cache cleared")
    
    async def health_check(self) -> Dict[str, Any]:
        try:
            return await LLMFactory.health_check_all(self.environment)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"error": str(e)}
    

