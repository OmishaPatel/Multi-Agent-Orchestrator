from .ollama_llm import OllamaLLM
from ..monitoring.model_monitor import SimpleModelMonitor
try:
    from ..monitoring.mlflow import SimpleMLflowTracker
except ImportError:
    SimpleMLflowTracker = None
from typing import Optional, List, Any, Dict
import time
import logging

logger = logging.getLogger(__name__)

class SimpleMonitoredLLM(OllamaLLM): 
    # Pydantic field declarations
    model_monitor: Optional[SimpleModelMonitor] = None
    mlflow_tracker: Optional[SimpleMLflowTracker] = None
    agent_type: str = "unknown"
    enable_mlflow: bool = False  # Disabled by default for simplicity
    
    def __init__(
        self,
        model_name: str,
        agent_type: str = "unknown",
        model_monitor: Optional[SimpleModelMonitor] = None,
        enable_mlflow: bool = False,
        **kwargs
    ):
        # Filter out monitoring-specific parameters
        filtered_kwargs = {k: v for k, v in kwargs.items() 
                          if k not in ['model_monitor', 'agent_type', 'enable_mlflow']}
        
        super().__init__(
            model_name=model_name,
            agent_type=agent_type,
            model_monitor=model_monitor,
            enable_mlflow=enable_mlflow,
            **filtered_kwargs
        )
        
        # Initialize simple monitoring if not provided
        if self.model_monitor is None:
            self.model_monitor = SimpleModelMonitor()
        
        if self.enable_mlflow and SimpleMLflowTracker is not None:
            self.mlflow_tracker = SimpleMLflowTracker()
        elif self.enable_mlflow:
            logger.warning("MLflow not available, disabling MLflow tracking")
    
    async def _acall(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> str:
        
        start_time = time.time()
        
        # Start MLflow run if enabled
        mlflow_run_id = None
        if self.enable_mlflow and self.mlflow_tracker:
            mlflow_run_id = self.mlflow_tracker.start_run(
                run_name=f"{self.model_name}_{int(start_time)}"
            )
            self.mlflow_tracker.log_model_info(
                self.model_name, self.environment, self.agent_type
            )
        
        try:
            # Call parent implementation
            response = await super()._acall(prompt, stop, run_manager, **kwargs)
            
            # Calculate basic metrics
            end_time = time.time()
            latency = end_time - start_time
            total_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(response)
            
            # Record simple inference metrics
            self.model_monitor.record_inference(
                model_name=self.model_name,
                agent_type=self.agent_type,
                environment=self.environment,
                total_tokens=total_tokens,
                latency=latency,
                success=True
            )
            
            # Log to MLflow (basic metrics only)
            if self.enable_mlflow and self.mlflow_tracker:
                self.mlflow_tracker.log_basic_metrics({
                    "latency": latency,
                    "total_tokens": total_tokens,
                    "tokens_per_second": total_tokens / latency if latency > 0 else 0
                })
            
            return response
            
        except Exception as e:
            # Record failed inference
            end_time = time.time()
            latency = end_time - start_time
            
            self.model_monitor.record_inference(
                model_name=self.model_name,
                agent_type=self.agent_type,
                environment=self.environment,
                total_tokens=0,
                latency=latency,
                success=False,
                error_type=type(e).__name__
            )
            
            raise
            
        finally:
            # End MLflow run
            if self.enable_mlflow and self.mlflow_tracker and mlflow_run_id:
                self.mlflow_tracker.end_run()
    
    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
    
    def get_simple_stats(self) -> Dict[str, Any]:
        base_metrics = self.get_metrics()
        monitor_stats = self.model_monitor.get_model_performance(self.model_name)
        resource_stats = self.model_monitor.get_resource_usage()
        
        return {
            "model_name": self.model_name,
            "agent_type": self.agent_type,
            "environment": self.environment,
            "basic_metrics": base_metrics,
            "performance": monitor_stats,
            "resources": resource_stats,
            "timestamp": time.time()
        }
