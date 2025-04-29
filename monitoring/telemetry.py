import os
import logging
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
import threading
from pympler import asizeof
from ..config.settings import settings

logger = logging.getLogger(__name__)

class Telemetry:
    """Collects and reports telemetry data for the agent"""
    
    def __init__(self, metrics_path: Optional[str] = None):
        self.metrics_path = metrics_path or settings.monitoring.metrics_path
        self.metrics = {
            "system": {},
            "agent": {
                "iterations": 0,
                "actions": 0,
                "successful_actions": 0,
                "failed_actions": 0,
                "tokens_generated": 0,
                "tokens_processed": 0,
            },
            "model": {
                "inference_count": 0,
                "inference_time": 0.0,
                "avg_inference_time": 0.0,
                "tokens_per_second": 0.0,
            },
            "memory": {
                "current_usage_mb": 0,
                "peak_usage_mb": 0,
            },
            "filesystem": {
                "files_created": 0,
                "files_modified": 0,
                "files_deleted": 0,
                "total_file_size_kb": 0,
            },
            "executor": {
                "executions": 0,
                "successful_executions": 0,
                "failed_executions": 0,
                "total_execution_time": 0.0,
                "avg_execution_time": 0.0,
            }
        }
        self._collection_thread = None
        self._stop_collection = threading.Event()
        self._lock = threading.Lock()
        self._collection_interval = 60  # seconds
        
        # Initialize if metrics path provided
        if self.metrics_path:
            os.makedirs(os.path.dirname(self.metrics_path), exist_ok=True)
    
    def start_collection(self) -> None:
        """Start collecting telemetry data"""
        if not settings.monitoring.telemetry_enabled:
            logger.info("Telemetry collection disabled")
            return
            
        logger.info("Starting telemetry collection")
        self._stop_collection.clear()
        self._collection_thread = threading.Thread(target=self._collect_data)
        self._collection_thread.daemon = True
        self._collection_thread.start()
    
    def stop_collection(self) -> None:
        """Stop collecting telemetry data"""
        if not self._collection_thread:
            return
            
        logger.info("Stopping telemetry collection")
        self._stop_collection.set()
        self._collection_thread.join(timeout=2.0)
        self._collection_thread = None
        
        # Save final metrics
        self._save_metrics()
    
    def record_agent_iteration(self) -> None:
        """Record an agent iteration"""
        with self._lock:
            self.metrics["agent"]["iterations"] += 1
    
    def record_agent_action(self, success: bool) -> None:
        """Record an agent action"""
        with self._lock:
            self.metrics["agent"]["actions"] += 1
            if success:
                self.metrics["agent"]["successful_actions"] += 1
            else:
                self.metrics["agent"]["failed_actions"] += 1
    
    def record_token_usage(self, generated: int, processed: int) -> None:
        """Record token usage"""
        with self._lock:
            self.metrics["agent"]["tokens_generated"] += generated
            self.metrics["agent"]["tokens_processed"] += processed
    
    def record_model_inference(self, time_taken: float, tokens: int) -> None:
        """Record model inference stats"""
        with self._lock:
            self.metrics["model"]["inference_count"] += 1
            self.metrics["model"]["inference_time"] += time_taken
            
            # Update averages
            count = self.metrics["model"]["inference_count"]
            total_time = self.metrics["model"]["inference_time"]
            
            self.metrics["model"]["avg_inference_time"] = total_time / count
            
            if time_taken > 0:
                self.metrics["model"]["tokens_per_second"] = tokens / time_taken
    
    def record_file_operation(self, operation: str) -> None:
        """Record file operation"""
        with self._lock:
            if operation == "create":
                self.metrics["filesystem"]["files_created"] += 1
            elif operation == "modify":
                self.metrics["filesystem"]["files_modified"] += 1
            elif operation == "delete":
                self.metrics["filesystem"]["files_deleted"] += 1
    
    def record_code_execution(self, success: bool, time_taken: float) -> None:
        """Record code execution"""
        with self._lock:
            self.metrics["executor"]["executions"] += 1
            self.metrics["executor"]["total_execution_time"] += time_taken
            
            if success:
                self.metrics["executor"]["successful_executions"] += 1
            else:
                self.metrics["executor"]["failed_executions"] += 1
                
            # Update average
            count = self.metrics["executor"]["executions"]
            total_time = self.metrics["executor"]["total_execution_time"]
            
            if count > 0:
                self.metrics["executor"]["avg_execution_time"] = total_time / count
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        with self._lock:
            return self.metrics.copy()
    
    def reset_metrics(self) -> None:
        """Reset metrics to initial state"""
        with self._lock:
            self.metrics = {
                "system": {},
                "agent": {
                    "iterations": 0,
                    "actions": 0,
                    "successful_actions": 0,
                    "failed_actions": 0,
                    "tokens_generated": 0,
                    "tokens_processed": 0,
                },
                "model": {
                    "inference_count": 0,
                    "inference_time": 0.0,
                    "avg_inference_time": 0.0,
                    "tokens_per_second": 0.0,
                },
                "memory": {
                    "current_usage_mb": 0,
                    "peak_usage_mb": 0,
                },
                "filesystem": {
                    "files_created": 0,
                    "files_modified": 0,
                    "files_deleted": 0,
                    "total_file_size_kb": 0,
                },
                "executor": {
                    "executions": 0,
                    "successful_executions": 0,
                    "failed_executions": 0,
                    "total_execution_time": 0.0,
                    "avg_execution_time": 0.0,
                }
            }
    
    def _collect_data(self) -> None:
        """Collect telemetry data at regular intervals"""
        while not self._stop_collection.is_set():
            try:
                # Collect system metrics
                self._collect_system_metrics()
                
                # Collect memory metrics
                self._collect_memory_metrics()
                
                # Collect filesystem metrics
                self._collect_filesystem_metrics()
                
                # Save metrics to file
                self._save_metrics()
                
            except Exception as e:
                logger.error(f"Error collecting telemetry data: {e}")
                
            # Wait for next collection interval
            self._stop_collection.wait(self._collection_interval)
    
    def _collect_system_metrics(self) -> None:
        """Collect system metrics"""
        import psutil
        
        with self._lock:
            # CPU usage
            self.metrics["system"]["cpu_percent"] = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.metrics["system"]["memory_percent"] = memory.percent
            self.metrics["system"]["memory_available_mb"] = memory.available / (1024 * 1024)
            self.metrics["system"]["memory_used_mb"] = memory.used / (1024 * 1024)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.metrics["system"]["disk_percent"] = disk.percent
            self.metrics["system"]["disk_free_gb"] = disk.free / (1024 * 1024 * 1024)
            
            # Network
            net_io = psutil.net_io_counters()
            self.metrics["system"]["network_sent_mb"] = net_io.bytes_sent / (1024 * 1024)
            self.metrics["system"]["network_recv_mb"] = net_io.bytes_recv / (1024 * 1024)
            
            # Process
            process = psutil.Process(os.getpid())
            self.metrics["system"]["process_cpu_percent"] = process.cpu_percent(interval=1)
            self.metrics["system"]["process_memory_mb"] = process.memory_info().rss / (1024 * 1024)
            self.metrics["system"]["process_threads"] = process.num_threads()
    
    def _collect_memory_metrics(self) -> None:
        """Collect memory usage of the application"""
        try:
            import gc
            
            # Force garbage collection
            gc.collect()
            
            # Estimate memory usage
            with self._lock:
                # Estimate memory usage of important components
                self.metrics["memory"]["current_usage_mb"] = asizeof.asizeof(self) / (1024 * 1024)
                
                # Update peak usage
                if self.metrics["memory"]["current_usage_mb"] > self.metrics["memory"]["peak_usage_mb"]:
                    self.metrics["memory"]["peak_usage_mb"] = self.metrics["memory"]["current_usage_mb"]
                    
        except Exception as e:
            logger.error(f"Error collecting memory metrics: {e}")
    
    def _collect_filesystem_metrics(self) -> None:
        """Collect filesystem metrics"""
        if not hasattr(self, "workspace_path"):
            return
            
        try:
            total_size = 0
            
            with self._lock:
                # Walk workspace to calculate file sizes
                for root, _, files in os.walk(self.workspace_path):
                    for file in files:
                        filepath = os.path.join(root, file)
                        try:
                            total_size += os.path.getsize(filepath)
                        except:
                            pass
                
                self.metrics["filesystem"]["total_file_size_kb"] = total_size / 1024
                
        except Exception as e:
            logger.error(f"Error collecting filesystem metrics: {e}")
    
    def _save_metrics(self) -> None:
        """Save metrics to file"""
        if not self.metrics_path:
            return
            
        try:
            with self._lock:
                metrics_data = {
                    "timestamp": datetime.now().isoformat(),
                    "metrics": self.metrics
                }
                
                with open(self.metrics_path, 'w') as f:
                    json.dump(metrics_data, f, indent=2)
                    
        except Exception as e:
            logger.error(f"Error saving metrics to file: {e}")
