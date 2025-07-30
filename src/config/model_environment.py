import os
from typing import Dict, Optional
from enum import Enum

class Environment(Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class EnvironmentAwareModelConfig:
    """
    Manages model configuration across different environments.
    
    Development: Lightweight local models via Ollama
    Testing: Cloud models for realistic testing
    Production: Self-hosted models for performance
    """

    def __init__(self):
        self.environment = self._detect_environment()
        self.config = self._load_environment_config()

    def _detect_environment(self) -> Environment:
        env_name = os.getenv("ENVIRONMENT", "development").lower()

        try:
            return Environment(env_name)
        except ValueError:
            return Environment.DEVELOPMENT

    def _load_environment_config(self) -> Dict:
        if self.environment == Environment.DEVELOPMENT:
            return {
                "model_provider": "ollama",
                "base_url": "http://localhost:11434",
                "models": {
                    "planning": "phi3:mini",
                    "research": "phi3:mini",
                    "code": "phi3:mini"
                },
                "fallback_enabled": True,
                "resource_monitoring": True,
                "max_concurrent": 2
            }
        # elif self.environment == Environment.TESTING:
        #     return {
        #         "model_provider": "huggingface",
        #         "models": {
        #             "planning": "microsoft/DialoGPT-medium",
        #             "research": "microsoft/DialoGPT-medium",
        #             "code": "microsoft/DialoGPT-medium"
        #         },
        #         "fallback_enabled": True,
        #         "api_key": os.getenv("HF_API_KEY")
        #     }
        elif self.environment == Environment.TESTING:
            return {
                "model_provider": "openai",
                "models": {
                    "planning": "gpt-3.5-turbo",
                    "research": "gpt-3.5-turbo",
                    "code": "gpt-4o-mini"
                },
                "fallback_enabled": True,
                "api_key": os.getenv("OPENAI_API_KEY")
            }
        else: # production
            return {
                "model_provider": "vllm",
                "base_url": os.getenv("VLLM_BASE_URL", "http://localhost:8000"),
                "models": {
                    "planning": "deepseek-r1-distill-llama-8b",
                    "research": "mistral:7b",
                    "code": "codellama:7b"
                },
                "fallback_enabled": False,
                "load_balancing": True
            }

    def get_model_for_agent(self, agent_type: str) -> str:
        return self.config["models"].get(agent_type, self.config["models"]["planning"])

    def get_provider_config(self) -> Dict:
        return {
            "provider": self.config["model_provider"],
            "base_url": self.config.get("base_url"),
            "api_key": self.config.get("api_key"),
            "fallback_enabled": self.config.get("fallback_enabled", False)
        }
