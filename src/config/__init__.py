"""
Configuration module initialization with Ollama integration.
"""
from .ollama_config import OllamaModelManager
from .model_environment import EnvironmentAwareModelConfig
from .settings import Settings

model_config = EnvironmentAwareModelConfig()

if model_config.environment.value == "development":
    ollama_manager = OllamaModelManager(
        base_url=model_config.config.get("base_url", "http://localhost:11434")
    )

else:
    ollama_manager = None

__all__ = [
    "OllamaModelManager",
    "EnvironmentAwareModelConfig",
    "Settings",
    "model_config",
    "ollama_manager"
]