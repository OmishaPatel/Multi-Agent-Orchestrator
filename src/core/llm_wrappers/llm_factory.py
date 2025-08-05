import os
import asyncio
from typing import Dict, Any, Optional
from enum import Enum
from .base_llm import BaseLLMWrapper
from .ollama_llm import OllamaLLM
from .throttled_ollama_llm import ThrottledOllamaLLM
try:
    from .huggingface_llm import HuggingFaceLLM
except ImportError:
    HuggingFaceLLM = None

try:
    from .openai_llm import OpenAILLM
except ImportError:
    OpenAILLM = None

try:
    from .featherless_llm import FeatherlessLLM
except ImportError:
    FeatherlessLLM = None

try:
    from .vllm_llm import vLLMLLM
except ImportError:
    vLLMLLM = None

class AgentType(Enum):
    PLANNING = "planning"
    RESEARCH = "research"
    CODE = "code"

class ModelEnvironment(Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

class LLMFactory:
    """
    Factory class for creating environment-appropriate LLM instances
    Handles model selection based on environment and agent type
    """
    
    # Request throttling for Ollama to prevent concurrent request issues
    _ollama_semaphore = asyncio.Semaphore(1)  # Only 1 concurrent request to Ollama
    
    # Model configurations for different environments
    MODEL_CONFIGS = {
        ModelEnvironment.DEVELOPMENT: {
            AgentType.PLANNING: {"model": "phi3:mini", "wrapper": ThrottledOllamaLLM},
            AgentType.RESEARCH: {"model": "llama3.2:1b", "wrapper": ThrottledOllamaLLM},
            AgentType.CODE: {"model": "qwen2:0.5b", "wrapper": ThrottledOllamaLLM},
        },
        ModelEnvironment.TESTING: {
            AgentType.PLANNING: {"model": "gpt-3.5-turbo", "wrapper": OpenAILLM},
            AgentType.RESEARCH: {"model": "gpt-3.5-turbo", "wrapper": OpenAILLM},
            AgentType.CODE: {"model": "gpt-4o-mini", "wrapper": OpenAILLM},
        },
        ModelEnvironment.PRODUCTION: {
            AgentType.PLANNING: {"model": "meta-llama/Llama-2-7b-chat-hf", "wrapper": vLLMLLM},
            AgentType.RESEARCH: {"model": "mistralai/Mistral-7B-Instruct-v0.1", "wrapper": vLLMLLM},
            AgentType.CODE: {"model": "codellama/CodeLlama-7b-Instruct-hf", "wrapper": vLLMLLM},
        }
    }
    
    @classmethod
    def create_llm(
        cls,
        agent_type: AgentType,
        environment: Optional[ModelEnvironment] = None,
        **kwargs
    ) -> BaseLLMWrapper:
        """Create an LLM instance for the specified agent type and environment"""
        
        # Determine environment from env var if not specified
        if environment is None:
            env_str = os.getenv("ENVIRONMENT", "development").lower()
            environment = ModelEnvironment(env_str)
        
        # Get model configuration
        config = cls.MODEL_CONFIGS[environment][agent_type]
        wrapper_class = config["wrapper"]
        model_name = config["model"]
        
        # Check if wrapper is available
        if wrapper_class is None:
            raise ImportError(f"Wrapper for {environment.value} environment not available")
        
        # Environment-specific parameters
        env_params = cls._get_environment_params(environment)
        
        # Merge with user-provided kwargs
        params = {**env_params, **kwargs, "model_name": model_name}
        
        # Create and return LLM instance
        return wrapper_class(**params)
    
    @classmethod
    def _get_environment_params(cls, environment: ModelEnvironment) -> Dict[str, Any]:
        
        if environment == ModelEnvironment.DEVELOPMENT:
            return {
                "max_retries": 2,
                "timeout": 90.0,  # Increased timeout for local Ollama models
                "enable_caching": True,
            }
        elif environment == ModelEnvironment.TESTING:
            return {
                "max_retries": 3,
                "timeout": 60.0,
                "enable_caching": True,
            }
        elif environment == ModelEnvironment.PRODUCTION:
            return {
                "max_retries": 3,
                "timeout": 45.0,
                "enable_caching": True,
            }
        
        return {}
    
    @classmethod
    def get_available_models(cls, environment: ModelEnvironment) -> Dict[AgentType, str]:
        return {
            agent_type: config["model"]
            for agent_type, config in cls.MODEL_CONFIGS[environment].items()
        }
    
    @classmethod
    async def health_check_all(cls, environment: ModelEnvironment) -> Dict[str, Any]:
        results = {}
        
        for agent_type in AgentType:
            try:
                llm = cls.create_llm(agent_type, environment)
                
                # Perform environment-specific health check
                if isinstance(llm, (OllamaLLM, ThrottledOllamaLLM)):
                    available = await llm.check_model_availability()
                    results[agent_type.value] = {"available": available, "type": "ollama"}
                elif OpenAILLM and isinstance(llm, OpenAILLM):
                    # OpenAI LLM doesn't have specific health check methods
                    # We just verify it was created successfully
                    results[agent_type.value] = {"status": "created", "type": "openai"}
                elif vLLMLLM and isinstance(llm, vLLMLLM):
                    health = await llm.check_server_health()
                    results[agent_type.value] = {"health": health, "type": "vllm"}
                else:
                    results[agent_type.value] = {"status": "unknown", "type": "unknown"}
                
            except Exception as e:
                results[agent_type.value] = {"error": str(e)}
        
        return results