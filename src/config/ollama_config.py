import asyncio
import logging
import os
import psutil
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


logger = logging.getLogger(__name__)

class ModelSize(Enum):
    """Model size categories for resource management"""
    TINY = "tiny" # <1gb
    SMALL = "small" # 1-3gb
    MEDIUM = "medium" # 3-8gb
    LARGE = "large" #>8gb


@dataclass
class ModelConfig:
    """Configuration for specific model"""
    name: str
    ollama_name: str
    size_gb: float
    ram_requirement: float
    category: ModelSize
    use_cases: List[str]
    description: str

class OllamaModelManager:
    """
    Manages Ollama models with resource awareness and automatic switching.
    
    Key responsibilities:
    - Monitor system resources
    - Select appropriate models based on available RAM
    - Handle model loading/unloading
    - Provide fallback mechanisms
    """
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.current_model: Optional[str] = None
        self.models = self._define_model_catalog()
        self.max_ram_usage = self._calculate_max_ram_usage()


    def _define_model_catalog(self) -> Dict[str, ModelConfig]:
        """
        Define available models optimized for 16GB RAM constraint.
        
        Model selection rationale:
        - Phi3:mini: Microsoft's efficient 3.8B parameter model, excellent reasoning
        - Llama3.2:1b: Meta's ultra-lightweight model for basic tasks
        - Qwen2:0.5b: Alibaba's tiny model for minimal resource usage
        """
        return {
            "phi3-mini": ModelConfig(
                name="phi3-mini",
                ollama_name="phi3-mini",
                size_gb=2.2,
                ram_requirement=2.5,
                category=ModelSize.SMALL,
                use_cases=["planning", "reasoning", "general"],
                description="Microsoft Phi3 Mini - Best balance of capability and efficiency"
            ),
            "llama3.2-1b": ModelConfig(
                name="llama3.2-1b",
                ollama_name="llama3.2:1b",
                size_gb=0.7,
                ram_requirement=1.0,
                category=ModelSize.TINY,
                use_cases=["simple_tasks", "testing"],
                description="Meta Llama 3.2 1B - Ultra-lightweight for basic tasks"
            ),
            "qwen2-0.5b": ModelConfig(
                name="quen2-0.5b",
                ollama_name="qwen2:0.5b",
                size_gb=0.3,
                ram_requirement=0.5,
                category=ModelSize.TINY,
                use_cases=["minimal", "emergency"],
                description="Qwen2 0.5B - Minimal resource usage fallback"
            )
        }

    def _calculate_max_ram_usage(self) -> float:
        total_ram = psutil.virtual_memory().total / (1024**3) # GB
        os_and_app_reserve = total_ram * 0.5 # 50% for system
        safety_buffer = 2.0

        max_model_ram = total_ram - os_and_app_reserve - safety_buffer
        logger.info(f"Total RAM: {total_ram:.1f}GB, Max model RAM: {max_model_ram:.1f}GB")

        return max_model_ram


    async def get_system_resources(self) -> Dict[str, float]:
        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)

        return {
            "total_ram_gb": memory.total / (1024**3),
            "available_ram_gb": memory.available / (1024**3),
            "used_ram_gb": memory.used/ (1024**3),
            "ram_percent": memory.percent,
            "cpu_percent": cpu
        }

    async def select_optimal_model(self, task_type: str = "general") -> str:
        resources = await self.get_system_resources()
        available_ram = resources["available_ram_gb"]

        # filter models that fit in available RAM
        suitable_models = [
            model for model in self.models.values()
            if model.ram_requirement <= available_ram
        ]

        if not suitable_models:
            logger.warning(f"No models fit in {available_ram:.1f}GB RAM")
            return self.models["qwen2-0.5b"].ollama_name # emergency fallback

        # For very low memory situations, prefer smallest model
        if available_ram < 1.5:  # Less than 1.5GB available
            smallest_model = min(suitable_models, key=lambda m: m.ram_requirement)
            logger.info(f"Low memory ({available_ram:.1f}GB), selecting smallest model: {smallest_model.name}")
            return smallest_model.ollama_name

        # Select best model for task type
        if task_type in ["planning", "reasoning"]:
            for model in suitable_models:
                if model.name == "phi3-mini":
                    return model.ollama_name

        # Default to largest suitable model
        best_model = max(suitable_models, key=lambda m: m.ram_requirement)
        logger.info(f"Selected {best_model.name} for {task_type} task")

        return best_model.ollama_name


    async def ensure_model_available(self, model_name: str) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                available_models = [m["name"] for m in response.json().get("models", [])]
                if model_name in available_models:
                    logger.info(f"Model {model_name} already available")
                    return True

            # pull model if not available

            logger.info(f"Pulling model {model_name}...")
            pull_response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name}
            )

            if pull_response.status_code == 200:
                logger.info(f"Successfully pulled {model_name}")
                return True

            else:
                logger.error(f"Failed to pull {model_name}: {pull_response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"Error ensuring model availability: {e}")
            return False

    async def generate_response(self, prompt: str, model: Optional[str] = None) -> str:
        if not model:
            model = await self.select_optimal_model()

        #ensure model is available
        if not await self.ensure_model_available(model):
            #fallback to smallest model
            model = self.models["qwen2-0.5b"].ollama_name
            await self.ensure_model_available(model)

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout = 30
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")

            else:
                logger.error(f"Generation failed: {response.text}")
                return "Error: Failed to generate response"

        except requests.RequestException as e:
            logger.error(f"Request error: {e}")
            return f"Error: {str(e)}"