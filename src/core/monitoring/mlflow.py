import warnings
# Suppress all deprecation and user warnings to clean up output
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*Pydantic.*")
warnings.filterwarnings("ignore", message=".*pkg_resources.*")
warnings.filterwarnings("ignore", message=".*google.*")

import mlflow
from typing import Dict, Any, Optional
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

class SimpleMLflowTracker:
    def __init__(
        self,
        tracking_uri: Optional[str] = None,
        experiment_name: str = "clarity-ai"
    ):
        # Set up local MLflow tracking
        if tracking_uri:
            # Handle Windows paths properly
            if tracking_uri.startswith("file://"):
                # Convert to proper file URI format
                path_part = tracking_uri.replace("file://", "")
                tracking_dir = Path(path_part)
                tracking_dir.mkdir(parents=True, exist_ok=True)
                # Use file:// prefix with forward slashes for cross-platform compatibility
                uri = tracking_dir.as_uri()
                mlflow.set_tracking_uri(uri)
            else:
                mlflow.set_tracking_uri(tracking_uri)
        else:
            # Default to local file store
            tracking_dir = Path("data/mlflow").resolve()  # Make absolute
            tracking_dir.mkdir(parents=True, exist_ok=True)
            # Use file:// prefix with forward slashes for cross-platform compatibility
            uri = tracking_dir.as_uri()
            mlflow.set_tracking_uri(uri)
        
        # Set experiment
        try:
            self.experiment = mlflow.set_experiment(experiment_name)
            logger.info(f"MLflow experiment set: {experiment_name}")
        except Exception as e:
            logger.error(f"Failed to set MLflow experiment: {e}")
            self.experiment = None
    
    def start_run(self, run_name: Optional[str] = None) -> Optional[str]:
        try:
            run = mlflow.start_run(run_name=run_name)
            logger.info(f"Started MLflow run: {run.info.run_id}")
            return run.info.run_id
        except Exception as e:
            logger.error(f"Failed to start MLflow run: {e}")
            return None
    
    def log_basic_metrics(self, metrics: Dict[str, float]):
        try:
            for metric_name, value in metrics.items():
                mlflow.log_metric(metric_name, value)
        except Exception as e:
            logger.error(f"Failed to log metrics: {e}")
    
    def log_model_info(self, model_name: str, environment: str, agent_type: str):
        try:
            mlflow.log_params({
                "model_name": model_name,
                "environment": environment,
                "agent_type": agent_type
            })
        except Exception as e:
            logger.error(f"Failed to log model info: {e}")
    
    def end_run(self):
        try:
            mlflow.end_run()
        except Exception as e:
            logger.error(f"Failed to end MLflow run: {e}")
