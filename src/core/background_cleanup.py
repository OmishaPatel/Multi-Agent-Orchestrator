import logging
import signal
import sys
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from src.core.state_recovery import StateRecoveryManager
from src.core.redis_state_manager import RedisStateManager
from src.config.cleanup_config import CleanupConfig
import atexit
import threading

logger = logging.getLogger(__name__)

class BackgroundCleanupService:
    """Background service for automated checkpoint cleanup"""
    
    def __init__(self, config: CleanupConfig = None):

        self.config = config or CleanupConfig.from_env()

        if not self.config.cleanup_enabled:
            logger.info("Cleanup service disabled by configuration")
            return

        self.cleanup_interval_hours = self.config.cleanup_interval_hours
        self.max_age_hours = self.config.max_age_hours
        self.scheduler = BackgroundScheduler(daemon=True)
        self.redis_state_manager = RedisStateManager()
        self.recovery_manager = StateRecoveryManager(self.redis_state_manager)
        self.is_running = False
        self._cleanup_lock = threading.Lock()
        
        # Register shutdown handler
        atexit.register(self.shutdown)
    
    def start(self):
        if self.is_running:
            logger.warning("Cleanup service is already running")
            return
        
        try:
            # Schedule cleanup every N hours
            self.scheduler.add_job(
                func=self._run_cleanup,
                trigger=IntervalTrigger(hours=self.cleanup_interval_hours),
                id='checkpoint_cleanup',
                name='Checkpoint Cleanup',
                replace_existing=True,
                max_instances=1  # Prevent overlapping cleanup runs
            )
            
            # Schedule daily stats logging at 2 AM
            self.scheduler.add_job(
                func=self._log_stats,
                trigger=CronTrigger(hour=2, minute=0),
                id='cleanup_stats',
                name='Cleanup Statistics',
                replace_existing=True
            )
            
            self.scheduler.start()
            self.is_running = True
            
            logger.info(f"Background cleanup service started - running every {self.cleanup_interval_hours} hours")
            
            # Run initial cleanup after 1 minute
            self.scheduler.add_job(
                func=self._run_cleanup,
                trigger='date',
                run_date=None,  # Run immediately
                id='initial_cleanup'
            )
            
        except Exception as e:
            logger.error(f"Failed to start cleanup service: {e}")
            raise
    
    def stop(self):
        if not self.is_running:
            return
        
        try:
            # Force shutdown with a timeout
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("Background cleanup service stopped")
        except Exception as e:
            logger.error(f"Error stopping cleanup service: {e}")
    
    def shutdown(self):
        self.stop()
    
    def _run_cleanup(self):
        with self._cleanup_lock:
            try:
                # Check if we should run in quiet mode
                import os
                quiet_mode = os.getenv("QUIET_TERMINAL", "true").lower() == "true"
                
                if not quiet_mode:
                    logger.info("Starting scheduled checkpoint cleanup")
                
                stats = self.recovery_manager.cleanup_expired_states(self.max_age_hours)
                
                # Only log if there's actual work done or errors, or if not in quiet mode
                if not quiet_mode or stats['checkpoints_deleted'] > 0 or stats['threads_deleted'] > 0 or stats['errors']:
                    logger.info(
                        f"Cleanup completed: {stats['checkpoints_deleted']} checkpoints deleted, "
                        f"{stats['threads_deleted']} threads deleted in {stats['cleanup_duration_seconds']:.2f}s"
                    )
                
                if stats['errors']:
                    logger.warning(f"Cleanup had {len(stats['errors'])} errors: {stats['errors']}")
                
            except Exception as e:
                logger.error(f"Scheduled cleanup failed: {e}")
    
    def _log_stats(self):
        try:
            stats = self.recovery_manager.get_cleanup_stats()
            logger.info(
                f"Storage stats: {stats['total_threads']} threads, "
                f"{stats['total_checkpoints']} checkpoints, "
                f"oldest: {stats['oldest_checkpoint_age_hours']:.1f}h, "
                f"Redis memory: {stats['redis_memory_info'].get('used_memory_human', 'unknown')}"
            )
        except Exception as e:
            logger.error(f"Failed to log stats: {e}")
    
    def force_cleanup(self):
        logger.info("Manual cleanup triggered")
        self._run_cleanup()
    
    def get_status(self):
        return {
            "is_running": self.is_running,
            "cleanup_interval_hours": self.cleanup_interval_hours,
            "max_age_hours": self.max_age_hours,
            "next_cleanup": str(self.scheduler.get_job('checkpoint_cleanup').next_run_time) if self.is_running else None,
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": str(job.next_run_time)
                }
                for job in self.scheduler.get_jobs()
            ] if self.is_running else []
        }

# Global instance
cleanup_service = BackgroundCleanupService()
