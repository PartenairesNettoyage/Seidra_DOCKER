"""
SEIDRA GPU Monitor
Real-time RTX 3090 monitoring and optimization
"""

import asyncio
import math
import psutil
import time
from collections import deque
from typing import Deque, Dict, Any, Optional
from datetime import datetime

from core.config import settings

try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    print("⚠️ GPUtil not available, GPU monitoring disabled")

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("⚠️ PyTorch not available, CUDA monitoring disabled")

class GPUMonitor:
    """Real-time GPU monitoring for RTX 3090 optimization"""
    
    def __init__(self):
        self.monitoring = False
        self.monitor_task = None
        self.stats_history = []
        self.max_history = 100  # Keep last 100 readings
        self._inference_durations: Deque[float] = deque(maxlen=100)
        self._cuda_errors: Deque[Dict[str, Any]] = deque(maxlen=20)

        # Performance thresholds
        thresholds = settings.notification_thresholds
        self.temp_warning = thresholds.gpu_temperature_warning
        self.temp_critical = thresholds.gpu_temperature_critical
        self.memory_warning = thresholds.gpu_memory_warning
        self.memory_critical = thresholds.gpu_memory_critical
        
        # Current status
        self.current_status = {
            "gpu_available": GPU_AVAILABLE and TORCH_AVAILABLE,
            "gpu_name": "Unknown",
            "driver_version": "Unknown",
            "cuda_version": "Unknown",
            "temperature": 0,
            "utilization": 0,
            "memory_used": 0,
            "memory_total": 0,
            "memory_free": 0,
            "memory_max_allocated": 0,
            "inference_avg_seconds": None,
            "inference_samples": 0,
            "cuda_error_count": 0,
            "cuda_errors": [],
            "power_draw": 0,
            "fan_speed": 0,
            "last_update": datetime.utcnow().isoformat()
        }
    
    async def initialize(self):
        """Initialize GPU monitoring"""
        if not GPU_AVAILABLE:
            print("⚠️ GPU monitoring not available")
            return
        
        try:
            # Get GPU information
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]  # Assume RTX 3090 is first GPU
                self.current_status.update({
                    "gpu_name": gpu.name,
                    "memory_total": gpu.memoryTotal,
                })
                print(f"✅ GPU detected: {gpu.name}")
            
            # Get CUDA information if available
            if TORCH_AVAILABLE and torch.cuda.is_available():
                self.current_status.update({
                    "cuda_version": torch.version.cuda,
                    "gpu_name": torch.cuda.get_device_name(0),
                    "memory_total": torch.cuda.get_device_properties(0).total_memory // (1024*1024)  # MB
                })
                print(f"✅ CUDA available: {torch.version.cuda}")
            
        except Exception as e:
            print(f"⚠️ GPU initialization failed: {e}")
    
    async def start_monitoring(self):
        """Start continuous GPU monitoring"""
        if self.monitoring:
            return
        
        await self.initialize()
        
        if not GPU_AVAILABLE:
            return
        
        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        print("🔄 GPU monitoring started")
    
    async def stop_monitoring(self):
        """Stop GPU monitoring"""
        if not self.monitoring:
            return
        
        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        print("🛑 GPU monitoring stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                await self._update_stats()
                await asyncio.sleep(2)  # Update every 2 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ GPU monitoring error: {e}")
                await asyncio.sleep(5)  # Wait longer on error
    
    async def _update_stats(self):
        """Update GPU statistics"""
        try:
            current_time = datetime.utcnow()
            stats = {
                "timestamp": current_time.isoformat(),
                "gpu_available": False,
                "temperature": 0,
                "utilization": 0,
                "memory_used": 0,
                "memory_free": 0,
                "power_draw": 0,
                "fan_speed": 0
            }
            
            # Get GPU stats using GPUtil
            if GPU_AVAILABLE:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    stats.update({
                        "gpu_available": True,
                        "temperature": gpu.temperature,
                        "utilization": gpu.load * 100,
                        "memory_used": gpu.memoryUsed,
                        "memory_free": gpu.memoryFree,
                    })
            
            # Get additional stats using PyTorch
            if TORCH_AVAILABLE and torch.cuda.is_available():
                device_index = torch.cuda.current_device()
                try:
                    allocated_bytes = torch.cuda.memory_allocated(device_index)  # type: ignore[attr-defined]
                    max_allocated_bytes = torch.cuda.max_memory_allocated(device_index)  # type: ignore[attr-defined]
                    total_memory_bytes = torch.cuda.get_device_properties(device_index).total_memory
                except Exception as exc:  # pragma: no cover - defensive
                    self._record_cuda_error(exc)
                else:
                    stats.update({
                        "memory_used": int(allocated_bytes) // (1024 * 1024),  # MB
                        "memory_free": int(total_memory_bytes - allocated_bytes) // (1024 * 1024),  # MB
                        "memory_max_allocated": int(max_allocated_bytes) // (1024 * 1024),  # MB
                    })

            stats["inference_avg_seconds"] = self.get_average_inference_time()
            stats["inference_samples"] = len(self._inference_durations)
            stats["cuda_error_count"] = len(self._cuda_errors)
            stats["cuda_errors"] = list(self._cuda_errors)

            # Update current status
            self.current_status.update(stats)
            self.current_status["last_update"] = current_time.isoformat()
            
            # Add to history
            self.stats_history.append(stats)
            if len(self.stats_history) > self.max_history:
                self.stats_history.pop(0)
            
            # Check for warnings
            await self._check_warnings(stats)

        except Exception as e:
            print(f"⚠️ Failed to update GPU stats: {e}")
            self._record_cuda_error(e)

    def _record_cuda_error(self, error: Exception | str) -> None:
        message = str(error)
        if not message:
            message = "Unknown CUDA error"
        entry = {
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._cuda_errors.appendleft(entry)
        self.current_status["cuda_error_count"] = len(self._cuda_errors)
        self.current_status["cuda_errors"] = list(self._cuda_errors)

    def record_generation_metrics(
        self,
        *,
        duration: Optional[float] = None,
        throughput: Optional[float] = None,
        vram_delta: Optional[float] = None,
        vram_peak: Optional[float] = None,
    ) -> None:
        if duration is not None and isinstance(duration, (int, float)):
            duration_value = float(duration)
            if math.isfinite(duration_value) and duration_value >= 0:
                self._inference_durations.append(duration_value)
        if throughput is not None and isinstance(throughput, (int, float)) and math.isfinite(float(throughput)):
            self.current_status["last_generation_throughput"] = float(throughput)
        if vram_delta is not None and isinstance(vram_delta, (int, float)) and math.isfinite(float(vram_delta)):
            self.current_status["last_generation_vram_delta_mb"] = float(vram_delta)
        if vram_peak is not None and isinstance(vram_peak, (int, float)) and math.isfinite(float(vram_peak)):
            self.current_status["last_generation_vram_peak_mb"] = float(vram_peak)

        if duration is not None and isinstance(duration, (int, float)):
            avg = self.get_average_inference_time()
            self.current_status["inference_avg_seconds"] = avg
            self.current_status["inference_samples"] = len(self._inference_durations)
        self.current_status["last_generation_timestamp"] = datetime.utcnow().isoformat()

    def get_average_inference_time(self) -> Optional[float]:
        if not self._inference_durations:
            return None
        return sum(self._inference_durations) / len(self._inference_durations)

    def get_cuda_error_stats(self) -> Dict[str, Any]:
        return {
            "count": len(self._cuda_errors),
            "recent": list(self._cuda_errors),
        }
    
    async def _check_warnings(self, stats: Dict[str, Any]):
        """Check for performance warnings"""
        warnings = []
        
        # Temperature warnings
        if stats["temperature"] > self.temp_critical:
            warnings.append(f"CRITICAL: GPU temperature {stats['temperature']}°C")
        elif stats["temperature"] > self.temp_warning:
            warnings.append(f"WARNING: GPU temperature {stats['temperature']}°C")
        
        # Memory warnings
        if stats["memory_used"] > 0 and self.current_status["memory_total"] > 0:
            memory_usage = stats["memory_used"] / self.current_status["memory_total"]
            if memory_usage > self.memory_critical:
                warnings.append(f"CRITICAL: GPU memory usage {memory_usage*100:.1f}%")
            elif memory_usage > self.memory_warning:
                warnings.append(f"WARNING: GPU memory usage {memory_usage*100:.1f}%")
        
        # Log warnings
        for warning in warnings:
            print(f"🚨 {warning}")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current GPU status"""
        return self.current_status.copy()
    
    async def get_history(self, minutes: int = 10) -> list:
        """Get GPU stats history"""
        if not self.stats_history:
            return []
        
        # Filter by time
        cutoff_time = datetime.utcnow().timestamp() - (minutes * 60)
        filtered_history = []
        
        for stat in self.stats_history:
            try:
                stat_time = datetime.fromisoformat(stat["timestamp"]).timestamp()
                if stat_time >= cutoff_time:
                    filtered_history.append(stat)
            except:
                continue
        
        return filtered_history
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance analysis"""
        if not self.stats_history:
            return {"error": "No data available"}
        
        recent_stats = self.stats_history[-10:]  # Last 10 readings
        
        if not recent_stats:
            return {"error": "No recent data"}
        
        # Calculate averages
        avg_temp = sum(s["temperature"] for s in recent_stats) / len(recent_stats)
        avg_util = sum(s["utilization"] for s in recent_stats) / len(recent_stats)
        avg_memory = sum(s["memory_used"] for s in recent_stats) / len(recent_stats)
        
        # Memory usage percentage
        memory_percent = 0
        if self.current_status["memory_total"] > 0:
            memory_percent = (avg_memory / self.current_status["memory_total"]) * 100
        
        # Performance assessment
        performance_score = 100
        if avg_temp > self.temp_warning:
            performance_score -= 20
        if memory_percent > 90:
            performance_score -= 30
        if avg_util < 50:
            performance_score -= 10  # Underutilized
        
        return {
            "average_temperature": round(avg_temp, 1),
            "average_utilization": round(avg_util, 1),
            "average_memory_usage": round(avg_memory, 1),
            "memory_usage_percent": round(memory_percent, 1),
            "performance_score": max(0, performance_score),
            "status": "optimal" if performance_score > 80 else "warning" if performance_score > 60 else "critical",
            "recommendations": self._get_recommendations(avg_temp, avg_util, memory_percent)
        }
    
    def _get_recommendations(self, temp: float, util: float, memory_percent: float) -> list:
        """Get performance recommendations"""
        recommendations = []
        
        if temp > self.temp_warning:
            recommendations.append("Consider improving GPU cooling or reducing workload")
        
        if memory_percent > 90:
            recommendations.append("Reduce batch size or enable CPU offloading to free VRAM")
        
        if util < 30:
            recommendations.append("GPU is underutilized - consider increasing batch size")
        
        if memory_percent < 50:
            recommendations.append("VRAM usage is low - can increase batch size for better performance")
        
        if not recommendations:
            recommendations.append("GPU performance is optimal")
        
        return recommendations
    
    async def optimize_for_generation(self) -> Dict[str, Any]:
        """Get optimization suggestions for image generation"""
        status = await self.get_status()
        
        if not status["gpu_available"]:
            return {
                "batch_size": 1,
                "use_cpu_offload": True,
                "use_attention_slicing": True,
                "recommendations": ["GPU not available, using CPU fallback"]
            }
        
        memory_total = status.get("memory_total", 24000)  # Assume 24GB for RTX 3090
        memory_used = status.get("memory_used", 0)
        memory_free = memory_total - memory_used
        
        # Determine optimal batch size based on available memory
        if memory_free > 20000:  # >20GB free
            batch_size = 4
            use_cpu_offload = False
        elif memory_free > 15000:  # >15GB free
            batch_size = 3
            use_cpu_offload = False
        elif memory_free > 10000:  # >10GB free
            batch_size = 2
            use_cpu_offload = True
        else:
            batch_size = 1
            use_cpu_offload = True
        
        return {
            "batch_size": batch_size,
            "use_cpu_offload": use_cpu_offload,
            "use_attention_slicing": memory_free < 15000,
            "use_half_precision": True,
            "memory_available": f"{memory_free}MB",
            "recommendations": [
                f"Optimal batch size: {batch_size}",
                f"CPU offloading: {'enabled' if use_cpu_offload else 'disabled'}",
                f"Available VRAM: {memory_free}MB"
            ]
        }
    
    async def cleanup(self):
        """Cleanup GPU monitoring resources"""
        await self.stop_monitoring()
        self.stats_history.clear()
        print("✅ GPU monitor cleaned up")