import time
import json
import asyncio
import psutil
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import deque
from pathlib import Path
import numpy as np
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

@dataclass
class SimpleInferenceMetric:
    timestamp: float
    model_name: str
    agent_type: str
    environment: str
    total_tokens: int
    latency: float
    success: bool
    error_type: Optional[str] = None

@dataclass
class SimpleResourceMetric:
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float

@dataclass
class SimpleModelStats:
    model_name: str
    total_requests: int
    successful_requests: int
    error_rate: float
    avg_latency: float
    p95_latency: float
    tokens_per_second: float
    last_updated: float

class SimpleModelMonitor:
    
    def __init__(
        self,
        storage_path: str = "data/monitoring",
        max_metrics_memory: int = 1000,
        drift_detection_window: int = 50
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # In-memory metrics storage (bounded)
        self.inference_metrics: deque = deque(maxlen=max_metrics_memory)
        self.resource_metrics: deque = deque(maxlen=max_metrics_memory)
        
        # Performance tracking
        self.model_stats: Dict[str, SimpleModelStats] = {}
        self.baseline_performance: Dict[str, Dict[str, float]] = {}
        
        # Drift detection
        self.drift_detection_window = drift_detection_window
        self.alerts: List[Dict[str, Any]] = []
        
        # Background monitoring
        self._monitoring_active = False
        self._resource_monitor_task = None
        self._lock = threading.Lock()
        
        # Load historical data
        self._load_historical_data()
    
    def start_monitoring(self):
        if not self._monitoring_active:
            self._monitoring_active = True
            self._resource_monitor_task = asyncio.create_task(self._resource_monitor_loop())
            logger.info("Simple model monitoring started")
    
    def stop_monitoring(self):
        self._monitoring_active = False
        if self._resource_monitor_task:
            self._resource_monitor_task.cancel()
        self._save_metrics_to_disk()
        logger.info("Simple model monitoring stopped")
    
    async def _resource_monitor_loop(self):
        while self._monitoring_active:
            try:
                await self._collect_resource_metrics()
                await asyncio.sleep(30)  # Collect every 10 seconds (less frequent)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(30)  # Back off on error
    
    async def _collect_resource_metrics(self):
        try:
            # CPU and Memory only
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            metric = SimpleResourceMetric(
                timestamp=time.time(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_gb=memory.used / (1024**3)
            )
            
            self.resource_metrics.append(metric)
            
            if cpu_percent > 80:
                self._generate_alert("warning", f"High CPU usage: {cpu_percent:.1f}%")
            
            if memory.percent > 85:
                self._generate_alert("critical", f"High memory usage: {memory.percent:.1f}%")
            
        except Exception as e:
            logger.error(f"Failed to collect resource metrics: {e}")
    
    def record_inference(
        self,
        model_name: str,
        agent_type: str,
        environment: str,
        total_tokens: int,
        latency: float,
        success: bool,
        error_type: Optional[str] = None
    ):
        
        metric = SimpleInferenceMetric(
            timestamp=time.time(),
            model_name=model_name,
            agent_type=agent_type,
            environment=environment,
            total_tokens=total_tokens,
            latency=latency,
            success=success,
            error_type=error_type
        )
        
        with self._lock:
            self.inference_metrics.append(metric)
            self._update_model_stats(metric)
        
        # Simple drift detection (non-blocking)
        asyncio.create_task(self._check_simple_drift(model_name))
    
    def _update_model_stats(self, metric: SimpleInferenceMetric):
        model_key = f"{metric.model_name}_{metric.environment}"
        
        if model_key not in self.model_stats:
            self.model_stats[model_key] = SimpleModelStats(
                model_name=metric.model_name,
                total_requests=0,
                successful_requests=0,
                error_rate=0.0,
                avg_latency=0.0,
                p95_latency=0.0,
                tokens_per_second=0.0,
                last_updated=time.time()
            )
        
        stats = self.model_stats[model_key]
        stats.total_requests += 1
        
        if metric.success:
            stats.successful_requests += 1
        
        stats.error_rate = 1.0 - (stats.successful_requests / stats.total_requests)
        stats.last_updated = time.time()
        
        # Calculate latency stats from recent metrics
        recent_latencies = [
            m.latency for m in self.inference_metrics
            if m.model_name == metric.model_name and m.success
        ]
        
        if recent_latencies:
            stats.avg_latency = np.mean(recent_latencies)
            stats.p95_latency = np.percentile(recent_latencies, 95)
            
            # Calculate tokens per second
            recent_throughput = [
                m.total_tokens / m.latency for m in self.inference_metrics
                if m.model_name == metric.model_name and m.success and m.latency > 0
            ]
            if recent_throughput:
                stats.tokens_per_second = np.mean(recent_throughput)
    
    async def _check_simple_drift(self, model_name: str):
        try:
            # Get recent metrics for this model
            recent_metrics = [
                m for m in list(self.inference_metrics)[-self.drift_detection_window:]
                if m.model_name == model_name and m.success
            ]
            
            if len(recent_metrics) < 10:  # Need at least 10 samples
                return
            
            # Calculate current performance
            current_latency = np.mean([m.latency for m in recent_metrics])
            current_error_rate = 1.0 - (
                sum(1 for m in recent_metrics if m.success) / len(recent_metrics)
            )
            
            # Compare with baseline (simple thresholds)
            baseline_key = f"{model_name}_baseline"
            if baseline_key in self.baseline_performance:
                baseline = self.baseline_performance[baseline_key]
                
                # Simple drift detection (2x latency increase or 20% error rate)
                if current_latency > baseline.get("latency", current_latency) * 2:
                    self._generate_alert(
                        "warning",
                        f"Performance drift: {model_name} latency increased significantly"
                    )
                
                if current_error_rate > 0.2:  # 20% error rate threshold
                    self._generate_alert(
                        "critical",
                        f"High error rate: {model_name} error rate is {current_error_rate:.1%}"
                    )
            else:
                # Establish simple baseline
                self.baseline_performance[baseline_key] = {
                    "latency": current_latency,
                    "error_rate": current_error_rate,
                    "established_at": time.time()
                }
                logger.info(f"Established baseline for {model_name}")
        
        except Exception as e:
            logger.error(f"Error checking drift: {e}")
    
    def _generate_alert(self, level: str, message: str):
        alert = {
            "timestamp": time.time(),
            "level": level,
            "message": message
        }
        
        self.alerts.append(alert)
        logger.log(
            logging.WARNING if level == "warning" else logging.ERROR,
            f"ALERT [{level.upper()}]: {message}"
        )
        
        # Keep only last 50 alerts
        if len(self.alerts) > 50:
            self.alerts = self.alerts[-50:]
    
    def get_model_performance(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        if model_name:
            matching_stats = {
                k: v for k, v in self.model_stats.items()
                if v.model_name == model_name
            }
        else:
            matching_stats = self.model_stats
        
        return {
            "models": {k: asdict(v) for k, v in matching_stats.items()},
            "last_updated": time.time()
        }
    
    def get_resource_usage(self, time_window_minutes: int = 30) -> Dict[str, Any]:
        cutoff_time = time.time() - (time_window_minutes * 60)
        recent_metrics = [
            m for m in self.resource_metrics if m.timestamp > cutoff_time
        ]
        
        if not recent_metrics:
            return {"error": "No recent resource data available"}
        
        cpu_values = [m.cpu_percent for m in recent_metrics]
        memory_values = [m.memory_percent for m in recent_metrics]
        
        return {
            "time_window_minutes": time_window_minutes,
            "cpu": {
                "avg": np.mean(cpu_values),
                "max": np.max(cpu_values),
                "current": cpu_values[-1] if cpu_values else 0
            },
            "memory": {
                "avg": np.mean(memory_values),
                "max": np.max(memory_values),
                "current": memory_values[-1] if memory_values else 0
            }
        }
    
    def get_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        return sorted(self.alerts, key=lambda x: x["timestamp"], reverse=True)[:limit]
    
    def _save_metrics_to_disk(self):
        try:
            # Save model stats only (simplified)
            stats_file = self.storage_path / "model_stats.json"
            with open(stats_file, 'w') as f:
                stats_data = {k: asdict(v) for k, v in self.model_stats.items()}
                json.dump(stats_data, f, indent=2)
            
            # Save baselines
            baseline_file = self.storage_path / "performance_baselines.json"
            with open(baseline_file, 'w') as f:
                json.dump(self.baseline_performance, f, indent=2)
            
            logger.info(f"Basic metrics saved to {self.storage_path}")
            
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    def _load_historical_data(self):
        try:
            # Load model stats
            stats_file = self.storage_path / "model_stats.json"
            if stats_file.exists():
                with open(stats_file, 'r') as f:
                    stats_data = json.load(f)
                    self.model_stats = {
                        k: SimpleModelStats(**v) for k, v in stats_data.items()
                    }
            
            # Load baselines
            baseline_file = self.storage_path / "performance_baselines.json"
            if baseline_file.exists():
                with open(baseline_file, 'r') as f:
                    self.baseline_performance = json.load(f)
            
            logger.info("Historical monitoring data loaded")
            
        except Exception as e:
            logger.error(f"Failed to load historical data: {e}")
    
    def get_summary(self) -> Dict[str, Any]:
        total_requests = sum(stats.total_requests for stats in self.model_stats.values())
        total_errors = sum(
            stats.total_requests - stats.successful_requests 
            for stats in self.model_stats.values()
        )
        
        recent_alerts = len([a for a in self.alerts if time.time() - a["timestamp"] < 3600])  # Last hour
        
        return {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": total_errors / max(1, total_requests),
            "active_models": len(self.model_stats),
            "recent_alerts": recent_alerts,
            "monitoring_active": self._monitoring_active,
            "last_updated": time.time()
        }
