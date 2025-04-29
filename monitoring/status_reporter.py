import time
import logging
import threading
import sys
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class StatusReporter:
    """Reports status of the agent's tasks"""
    
    def __init__(self):
        self.task_name = "Idle"
        self.status = "Not started"
        self.progress = 0
        self.total_steps = 0
        self.start_time = None
        self.end_time = None
        self.update_time = None
        self.success = None
        self.error = None
        self.history = []
        self._lock = threading.Lock()
        self._progress_thread = None
        self._stop_progress = threading.Event()
    
    def start_task(self, task_name: str, total_steps: int = 100) -> None:
        """Start a new task"""
        with self._lock:
            self.task_name = task_name
            self.status = "Running"
            self.progress = 0
            self.total_steps = total_steps
            self.start_time = datetime.now()
            self.end_time = None
            self.update_time = self.start_time
            self.success = None
            self.error = None
            
            # Add event to history
            self.history.append({
                "timestamp": self.start_time.isoformat(),
                "event": "start_task",
                "task_name": task_name,
                "total_steps": total_steps
            })
            
            # Log start of task
            logger.info(f"Started task: {task_name} ({total_steps} steps)")
            
            # Start progress thread
            self._stop_progress.clear()
            self._progress_thread = threading.Thread(target=self._progress_reporter)
            self._progress_thread.daemon = True
            self._progress_thread.start()
    
    def update_status(self, status: str) -> None:
        """Update the current status"""
        with self._lock:
            self.status = status
            self.update_time = datetime.now()
            
            # Add event to history
            self.history.append({
                "timestamp": self.update_time.isoformat(),
                "event": "update_status",
                "status": status
            })
            
            # Log status update
            logger.info(f"Status update: {status}")
    
    def increment_progress(self, steps: int = 1) -> None:
        """Increment the progress"""
        with self._lock:
            self.progress = min(self.progress + steps, self.total_steps)
            self.update_time = datetime.now()
            
            # Add event to history
            self.history.append({
                "timestamp": self.update_time.isoformat(),
                "event": "increment_progress",
                "progress": self.progress,
                "total_steps": self.total_steps
            })
    
    def complete_task(self) -> None:
        """Mark the task as complete"""
        with self._lock:
            self.progress = self.total_steps
            self.status = "Completed"
            self.end_time = datetime.now()
            self.update_time = self.end_time
            self.success = True
            
            # Add event to history
            self.history.append({
                "timestamp": self.end_time.isoformat(),
                "event": "complete_task",
                "duration": (self.end_time - self.start_time).total_seconds()
            })
            
            # Log task completion
            duration = (self.end_time - self.start_time).total_seconds()
            logger.info(f"Task completed: {self.task_name} (duration: {duration:.2f}s)")
            
            # Stop progress thread
            self._stop_progress.set()
            if self._progress_thread:
                self._progress_thread.join(timeout=1.0)
    
    def fail_task(self, error: str) -> None:
        """Mark the task as failed"""
        with self._lock:
            self.status = "Failed"
            self.end_time = datetime.now()
            self.update_time = self.end_time
            self.success = False
            self.error = error
            
            # Add event to history
            self.history.append({
                "timestamp": self.end_time.isoformat(),
                "event": "fail_task",
                "error": error,
                "duration": (self.end_time - self.start_time).total_seconds()
            })
            
            # Log task failure
            duration = (self.end_time - self.start_time).total_seconds()
            logger.error(f"Task failed: {self.task_name} (duration: {duration:.2f}s) - {error}")
            
            # Stop progress thread
            self._stop_progress.set()
            if self._progress_thread:
                self._progress_thread.join(timeout=1.0)
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status"""
        with self._lock:
            duration = None
            estimated_time_remaining = None
            
            if self.start_time:
                now = datetime.now()
                duration = (self.end_time or now - self.start_time).total_seconds()
                
                if self.progress > 0 and self.progress < self.total_steps:
                    time_per_step = duration / self.progress
                    steps_remaining = self.total_steps - self.progress
                    estimated_time_remaining = time_per_step * steps_remaining
            
            return {
                "task_name": self.task_name,
                "status": self.status,
                "progress": self.progress,
                "total_steps": self.total_steps,
                "percentage": int(100 * self.progress / self.total_steps) if self.total_steps > 0 else 0,
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "update_time": self.update_time.isoformat() if self.update_time else None,
                "end_time": self.end_time.isoformat() if self.end_time else None,
                "duration": duration,
                "estimated_time_remaining": estimated_time_remaining,
                "success": self.success,
                "error": self.error
            }
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Get the history of events"""
        with self._lock:
            return self.history.copy()
    
    def _progress_reporter(self) -> None:
        """Thread to periodically report progress"""
        while not self._stop_progress.is_set():
            with self._lock:
                if self.progress < self.total_steps:
                    percentage = int(100 * self.progress / self.total_steps) if self.total_steps > 0 else 0
                    elapsed = (datetime.now() - self.start_time).total_seconds()
                    
                    logger.info(f"Progress: {self.progress}/{self.total_steps} ({percentage}%) - {elapsed:.2f}s elapsed")
            
            # Wait before next update
            time.sleep(5)
