"""Telemetry aggregation and broadcasting for SEIDRA Ultimate.

This service periodically samples GPU, system and platform metrics so the
FastAPI API and WebSocket clients can expose a unified dashboard without each
endpoint querying the underlying services on demand.
"""
from __future__ import annotations

import asyncio
import platform
import socket
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Set

try:  # pragma: no cover - psutil is optional during tests
    import psutil  # type: ignore
    PSUTIL_AVAILABLE = True
except Exception:  # pragma: no cover - psutil missing in minimal envs
    psutil = None  # type: ignore
    PSUTIL_AVAILABLE = False

try:  # pragma: no cover - prometheus_client peut être absent
    from prometheus_client import Gauge, Histogram  # type: ignore
    PROMETHEUS_AVAILABLE = True
except Exception:  # pragma: no cover - instrumentation optionnelle
    Gauge = Histogram = None  # type: ignore
    PROMETHEUS_AVAILABLE = False

from core.config import NotificationThresholds, settings
from services.database import DatabaseService
from services.gpu_monitor import GPUMonitor
from services.model_manager import ModelManager
from services.websocket_manager import WebSocketManager


if PROMETHEUS_AVAILABLE:
    GENERATION_LATENCY = Histogram(
        "seidra_generation_latency_seconds",
        "Latence des générations IA",
        labelnames=("media_type", "priority"),
        buckets=(0.5, 1, 2, 4, 8, 16, 32, 64),
    )
    GENERATION_VRAM_PEAK = Gauge(
        "seidra_generation_vram_peak_mb",
        "VRAM maximale observée par génération (Mo)",
        labelnames=("media_type",),
    )
    GENERATION_VRAM_DELTA = Gauge(
        "seidra_generation_vram_delta_mb",
        "Variation de VRAM par génération (Mo)",
        labelnames=("media_type",),
    )
    GPU_VRAM_USED = Gauge(
        "seidra_gpu_vram_used_mb",
        "VRAM actuellement utilisée (Mo)",
        labelnames=("device",),
    )
    GPU_VRAM_FREE = Gauge(
        "seidra_gpu_vram_free_mb",
        "VRAM libre (Mo)",
        labelnames=("device",),
    )
    REMOTE_CALL_LATENCY = Histogram(
        "seidra_remote_call_latency_seconds",
        "Latence des appels aux services distants",
        labelnames=("service", "endpoint"),
        buckets=(0.1, 0.5, 1, 2, 4, 8, 16, 32, 64),
    )
    REMOTE_CALL_FAILURE_RATE = Gauge(
        "seidra_remote_call_failure_rate",
        "Taux d'échec des appels distants",
        labelnames=("service", "endpoint"),
    )
else:  # pragma: no cover - instrumentation inactive
    GENERATION_LATENCY = None
    GENERATION_VRAM_PEAK = None
    GENERATION_VRAM_DELTA = None
    GPU_VRAM_USED = None
    GPU_VRAM_FREE = None
    REMOTE_CALL_LATENCY = None
    REMOTE_CALL_FAILURE_RATE = None


class TelemetryService:
    """Collects runtime metrics and broadcasts them to interested clients."""

    def __init__(
        self,
        *,
        gpu_monitor: Optional[GPUMonitor] = None,
        model_manager: Optional[ModelManager] = None,
        websocket_manager: Optional[WebSocketManager] = None,
        notification_service: Optional["NotificationService"] = None,
        interval_seconds: int = 30,
        history_size: int = 120,
        thresholds: Optional[NotificationThresholds] = None,
    ) -> None:
        self.gpu_monitor = gpu_monitor
        self.model_manager = model_manager
        self.websocket_manager = websocket_manager
        self.notification_service = notification_service
        self.interval_seconds = max(5, interval_seconds)
        self._lock = asyncio.Lock()
        self._remote_lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._latest_snapshot: Optional[Dict[str, Any]] = None
        self._history: Deque[Dict[str, Any]] = deque(maxlen=history_size)
        self._recent_generation_metrics: Deque[Dict[str, Any]] = deque(maxlen=history_size)
        self._active_alerts: Set[str] = set()
        self.thresholds: NotificationThresholds = thresholds or settings.notification_thresholds
        self._prometheus_enabled = PROMETHEUS_AVAILABLE
        self._remote_stats: Dict[str, Dict[str, Any]] = {}
        self._remote_history: Deque[Dict[str, Any]] = deque(maxlen=history_size)

    async def start(self) -> None:
        """Start the telemetry sampling loop."""
        if self._running:
            return
        self._running = True
        # Prime the cache so early requests have data available.
        await self.collect_snapshot()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the telemetry sampling loop and cleanup."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:  # pragma: no cover - cancellation path
                pass
        self._task = None

    async def _run_loop(self) -> None:
        while self._running:
            try:
                snapshot = await self.collect_snapshot()
                if self.websocket_manager:
                    await self.websocket_manager.send_system_status(snapshot)
            except asyncio.CancelledError:  # pragma: no cover - task cancelled
                break
            except Exception as exc:  # pragma: no cover - safety net
                print(f"⚠️ Telemetry loop error: {exc}")
            await asyncio.sleep(self.interval_seconds)

    async def collect_snapshot(self) -> Dict[str, Any]:
        """Collect and cache a fresh telemetry snapshot."""
        async with self._lock:
            snapshot = await self._build_snapshot()
            self._latest_snapshot = snapshot
            self._history.append(snapshot)
            await self._process_alerts(snapshot)
            return snapshot

    async def get_snapshot(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Return the most recent snapshot, refreshing it if needed."""
        if force_refresh or self._latest_snapshot is None:
            return await self.collect_snapshot()
        return self._latest_snapshot

    async def get_gpu_history(self, minutes: int = 10) -> List[Dict[str, Any]]:
        if not self.gpu_monitor:
            return []
        try:
            return await self.gpu_monitor.get_history(minutes=minutes)
        except Exception:  # pragma: no cover - GPU monitor failure
            return []

    async def _build_snapshot(self) -> Dict[str, Any]:
        timestamp = datetime.utcnow().isoformat()

        gpu_status: Dict[str, Any] = {"gpu_available": False}
        gpu_performance: Dict[str, Any] = {}
        if self.gpu_monitor:
            try:
                gpu_status = await self.gpu_monitor.get_status()
                gpu_performance = await self.gpu_monitor.get_performance_metrics()
                error_stats = self.gpu_monitor.get_cuda_error_stats()
                gpu_status.setdefault("inference_avg_seconds", self.gpu_monitor.get_average_inference_time())
                gpu_status.setdefault("cuda_error_count", error_stats.get("count"))
                gpu_status.setdefault("cuda_errors", error_stats.get("recent"))
            except Exception:  # pragma: no cover - GPU monitor failure
                gpu_status = {"gpu_available": False}
                gpu_performance = {"error": "unavailable"}

        model_info: Dict[str, Any] = {}
        if self.model_manager:
            try:
                model_info = await self.model_manager.get_model_info()
            except Exception as exc:  # pragma: no cover - model manager failure
                model_info = {"error": str(exc)}

        db = DatabaseService()
        try:
            platform_stats = db.get_platform_summary()
            job_stats = db.get_job_statistics()
            media_stats = db.get_media_statistics()
        finally:
            db.close()

        connections: Dict[str, Any] = {}
        if self.websocket_manager:
            connections = self.websocket_manager.get_connection_stats()

        system_metrics = self._collect_system_metrics()

        generation_summary = await asyncio.to_thread(self._get_generation_metrics_summary)
        generation_summary["recent"] = list(self._recent_generation_metrics)
        if self.gpu_monitor:
            generation_summary["rollingLatencySeconds"] = self.gpu_monitor.get_average_inference_time()
            generation_summary["cudaErrors"] = self.gpu_monitor.get_cuda_error_stats()

        async with self._remote_lock:
            remote_summary = {}
            for service, stats in self._remote_stats.items():
                calls = stats.get("calls", 0)
                total_duration = stats.get("total_duration", 0.0)
                remote_summary[service] = {
                    "calls": calls,
                    "failures": stats.get("failures", 0),
                    "failureRate": stats.get("failure_rate", 0.0),
                    "avgLatencySeconds": (total_duration / calls) if calls else None,
                    "lastEndpoint": stats.get("last_endpoint"),
                    "lastDurationSeconds": stats.get("last_duration"),
                    "lastSuccess": stats.get("last_success"),
                    "lastAttempts": stats.get("last_attempts"),
                    "queueLength": stats.get("queue_length", 0),
                }
            remote_recent = list(self._remote_history)

        self._record_gpu_prometheus(gpu_status)

        snapshot: Dict[str, Any] = {
            "timestamp": timestamp,
            "gpu": gpu_status,
            "gpuPerformance": gpu_performance,
            "models": {
                "mode": model_info.get("mode"),
                "basePipelineLoaded": model_info.get("base_pipeline_loaded"),
                "availableLoras": model_info.get("available_loras", []),
                "optimalBatchSize": model_info.get("optimal_batch_size"),
                "metadata": model_info,
            },
            "jobs": job_stats,
            "media": media_stats,
            "platform": platform_stats,
            "connections": connections,
            "system": system_metrics,
            "generation": generation_summary,
            "remoteCalls": {
                "summary": remote_summary,
                "recent": remote_recent,
            },
        }
        return snapshot

    def _collect_system_metrics(self) -> Dict[str, Any]:
        cpu_percent = None
        memory_percent = None
        total_memory = None
        available_memory = None
        uptime_seconds = None

        if PSUTIL_AVAILABLE:
            try:
                cpu_percent = psutil.cpu_percent(interval=None)
                virtual_mem = psutil.virtual_memory()
                memory_percent = virtual_mem.percent
                total_memory = virtual_mem.total
                available_memory = virtual_mem.available
                uptime_seconds = time.time() - psutil.boot_time()
            except Exception:  # pragma: no cover - psutil runtime failure
                cpu_percent = memory_percent = None

        return {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpuPercent": cpu_percent,
            "memoryPercent": memory_percent,
            "memoryTotal": total_memory,
            "memoryAvailable": available_memory,
            "uptimeSeconds": uptime_seconds,
        }

    def get_history_snapshots(self, minutes: int) -> List[Dict[str, Any]]:
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        results: List[Dict[str, Any]] = []
        for entry in list(self._history):
            timestamp_str = entry.get("timestamp")
            if not timestamp_str:
                continue
            try:
                entry_time = datetime.fromisoformat(timestamp_str)
            except ValueError:
                continue
            if entry_time >= cutoff:
                results.append(entry)
        return results

    async def record_generation_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        stored = await asyncio.to_thread(self._store_generation_metric, metric)
        extracted = self._extract_generation_fields(stored)
        if self.gpu_monitor:
            self.gpu_monitor.record_generation_metrics(
                duration=extracted["latencySeconds"],
                throughput=extracted["throughput"],
                vram_delta=extracted["vramDeltaMB"],
                vram_peak=extracted["vramPeakMb"],
            )
        enriched = self._enrich_generation_metric(stored, **extracted)
        self._recent_generation_metrics.appendleft(enriched)
        if self.websocket_manager:
            await self.websocket_manager.dispatch_event(
                {
                    "type": "telemetry.generation",
                    "payload": enriched,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                channels={"system"},
            )
        self._record_generation_prometheus(metric, extracted)
        return enriched

    async def record_remote_call(
        self,
        service: str,
        endpoint: str,
        *,
        duration: float,
        success: bool,
        attempts: int,
        queue_length: int = 0,
    ) -> None:
        """Publie une mesure de latence/fiabilité pour un appel distant."""

        timestamp = datetime.utcnow().isoformat()
        entry = {
            "service": service,
            "endpoint": endpoint,
            "durationSeconds": duration,
            "success": success,
            "attempts": attempts,
            "queueLength": queue_length,
            "timestamp": timestamp,
        }

        async with self._remote_lock:
            stats = self._remote_stats.setdefault(
                service,
                {
                    "calls": 0,
                    "failures": 0,
                    "total_duration": 0.0,
                    "last_endpoint": None,
                    "last_duration": None,
                    "last_success": None,
                    "last_attempts": None,
                    "queue_length": 0,
                },
            )
            stats["calls"] += 1
            stats["total_duration"] += duration
            if not success:
                stats["failures"] += 1
            stats["last_endpoint"] = endpoint
            stats["last_duration"] = duration
            stats["last_success"] = success
            stats["last_attempts"] = attempts
            stats["queue_length"] = queue_length
            stats["failure_rate"] = (
                stats["failures"] / stats["calls"] if stats["calls"] else 0.0
            )
            self._remote_history.appendleft(entry)

        if self.websocket_manager:
            await self.websocket_manager.dispatch_event(
                {
                    "type": "telemetry.remote_call",
                    "payload": entry,
                    "timestamp": timestamp,
                },
                channels={"system"},
            )

        if self._prometheus_enabled:
            if REMOTE_CALL_LATENCY is not None:
                REMOTE_CALL_LATENCY.labels(service=service, endpoint=endpoint).observe(duration)
            if REMOTE_CALL_FAILURE_RATE is not None:
                REMOTE_CALL_FAILURE_RATE.labels(service=service, endpoint=endpoint).set(
                    stats["failure_rate"]
                )

    async def get_generation_metrics(
        self,
        *,
        limit: int = 50,
        minutes: Optional[int] = None,
        media_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = await asyncio.to_thread(
            self._fetch_generation_metrics, limit, minutes, media_type
        )
        data["recent"] = list(self._recent_generation_metrics)
        return data

    def _store_generation_metric(self, metric: Dict[str, Any]) -> Dict[str, Any]:
        db = DatabaseService()
        try:
            record = db.create_generation_metric(**metric)
            return db.serialize_generation_metric(record)
        finally:
            db.close()

    def _fetch_generation_metrics(
        self, limit: int, minutes: Optional[int], media_type: Optional[str]
    ) -> Dict[str, Any]:
        db = DatabaseService()
        try:
            items = db.list_generation_metrics(
                limit=limit, since_minutes=minutes, media_type=media_type
            )
            summary = db.aggregate_generation_metrics(
                since_minutes=minutes, media_type=media_type
            )
            return {
                "items": [db.serialize_generation_metric(item) for item in items],
                "summary": summary,
            }
        finally:
            db.close()

    def _get_generation_metrics_summary(self) -> Dict[str, Any]:
        db = DatabaseService()
        try:
            summary = db.aggregate_generation_metrics(since_minutes=60)
        finally:
            db.close()
        return summary

    def _extract_generation_fields(self, metric: Dict[str, Any]) -> Dict[str, Optional[float]]:
        latency_raw = metric.get("durationSeconds", metric.get("duration_seconds"))
        latency = float(latency_raw) if latency_raw is not None else None

        throughput_raw = metric.get("throughput")
        throughput = float(throughput_raw) if throughput_raw is not None else None

        vram_delta_raw = metric.get("vramDeltaMb", metric.get("vram_delta_mb"))
        vram_delta = float(vram_delta_raw) if vram_delta_raw is not None else None

        vram_peak_raw = metric.get("vramPeakMb", metric.get("vram_peak_mb"))
        vram_peak = float(vram_peak_raw) if vram_peak_raw is not None else None

        return {
            "latencySeconds": latency,
            "throughput": throughput,
            "vramDeltaMB": vram_delta,
            "vramPeakMb": vram_peak,
        }

    def _enrich_generation_metric(
        self,
        metric: Dict[str, Any],
        *,
        latencySeconds: Optional[float] = None,
        throughput: Optional[float] = None,
        vramDeltaMB: Optional[float] = None,
        vramPeakMb: Optional[float] = None,
    ) -> Dict[str, Any]:
        enriched = dict(metric)
        enriched["latencySeconds"] = latencySeconds
        enriched["throughput"] = throughput
        enriched["vramDeltaMB"] = vramDeltaMB
        if vramPeakMb is not None:
            enriched["vramPeakMb"] = vramPeakMb

        if self.gpu_monitor:
            avg_latency = self.gpu_monitor.get_average_inference_time()
            if avg_latency is not None:
                enriched["rollingLatencySeconds"] = avg_latency
            enriched["cudaErrors"] = self.gpu_monitor.get_cuda_error_stats()

        return enriched

    def _record_gpu_prometheus(self, gpu_status: Dict[str, Any]) -> None:
        if not self._prometheus_enabled or not GPU_VRAM_USED:
            return

        device_name = str(gpu_status.get("gpu_name") or "gpu0")
        used = gpu_status.get("memory_used") or gpu_status.get("memoryUsed")
        free = gpu_status.get("memory_free") or gpu_status.get("memoryFree")

        if isinstance(used, (int, float)):
            GPU_VRAM_USED.labels(device=device_name).set(float(used))
        if isinstance(free, (int, float)):
            GPU_VRAM_FREE.labels(device=device_name).set(float(free))

    def _record_generation_prometheus(
        self, metric: Dict[str, Any], extracted: Dict[str, Optional[float]]
    ) -> None:
        if not self._prometheus_enabled or not GENERATION_LATENCY:
            return

        media_type = str(metric.get("media_type") or "unknown").lower()
        extra = metric.get("extra") or {}
        priority = (
            extra.get("priorityTag")
            or extra.get("priority_tag")
            or extra.get("priority")
            or "normal"
        )
        priority_label = str(priority).lower()

        latency = extracted.get("latencySeconds")
        if isinstance(latency, (int, float)):
            GENERATION_LATENCY.labels(media_type=media_type, priority=priority_label).observe(
                float(latency)
            )

        peak = extracted.get("vramPeakMb")
        if peak is None:
            peak = metric.get("vram_peak_mb")
        if isinstance(peak, (int, float)) and GENERATION_VRAM_PEAK:
            GENERATION_VRAM_PEAK.labels(media_type=media_type).set(float(peak))

        delta = extracted.get("vramDeltaMB")
        if delta is None:
            delta = metric.get("vram_delta_mb")
        if isinstance(delta, (int, float)) and GENERATION_VRAM_DELTA:
            GENERATION_VRAM_DELTA.labels(media_type=media_type).set(float(delta))

    async def _process_alerts(self, snapshot: Dict[str, Any]) -> None:
        if not self.notification_service:
            return

        gpu = snapshot.get("gpu", {}) or {}
        performance = snapshot.get("gpuPerformance", {}) or {}
        system = snapshot.get("system", {}) or {}

        async def activate(
            key: str,
            level: str,
            title: str,
            message: str,
            *,
            metadata: Optional[Dict[str, Any]] = None,
        ) -> None:
            if key in self._active_alerts:
                return
            self._active_alerts.add(key)
            await self.notification_service.push(
                level,
                title,
                message,
                category="system",
                metadata=metadata or {},
            )

        async def deactivate(key: str, title: str, message: str) -> None:
            if key not in self._active_alerts:
                return
            self._active_alerts.remove(key)
            await self.notification_service.push(
                "info",
                title,
                message,
                category="system",
            )

        gpu_available = bool(gpu.get("gpu_available"))
        if not gpu_available:
            await activate(
                "gpu-offline",
                "warning",
                "GPU offline",
                "The GPU monitor does not detect any active device.",
                metadata={"gpu": gpu},
            )
        else:
            await deactivate(
                "gpu-offline",
                "GPU restored",
                "GPU monitoring reports a healthy device again.",
            )

        temperature = gpu.get("temperature")
        temp_warn = self.thresholds.gpu_temperature_warning
        temp_critical = max(self.thresholds.gpu_temperature_critical, temp_warn)
        if isinstance(temperature, (int, float)):
            if temperature >= temp_critical:
                await activate(
                    "gpu-temp-critical",
                    "error",
                    "GPU overheating",
                    f"GPU temperature reached {temperature}°C.",
                    metadata={"temperature": temperature},
                )
            else:
                await deactivate(
                    "gpu-temp-critical",
                    "GPU temperature normalised",
                    "GPU temperature fell below critical levels.",
                )
            if temperature >= temp_warn:
                await activate(
                    "gpu-temp-warning",
                    "warning",
                    "GPU temperature high",
                    f"GPU temperature is {temperature}°C.",
                    metadata={"temperature": temperature},
                )
            else:
                await deactivate(
                    "gpu-temp-warning",
                    "GPU temperature optimal",
                    "GPU temperature is within nominal range.",
                )

        memory_used = gpu.get("memory_used")
        memory_total = gpu.get("memory_total")
        if isinstance(memory_used, (int, float)) and isinstance(memory_total, (int, float)) and memory_total > 0:
            usage_ratio = memory_used / memory_total
            mem_critical = max(self.thresholds.gpu_memory_critical, self.thresholds.gpu_memory_warning)
            mem_warning = self.thresholds.gpu_memory_warning
            if usage_ratio >= mem_critical:
                await activate(
                    "gpu-memory-critical",
                    "error",
                    "GPU VRAM saturated",
                    f"GPU memory usage is at {usage_ratio * 100:.1f}%.",
                    metadata={"memory_used": memory_used, "memory_total": memory_total},
                )
            else:
                await deactivate(
                    "gpu-memory-critical",
                    "GPU memory headroom recovered",
                    "GPU memory usage dropped below the critical threshold.",
                )
            if usage_ratio >= mem_warning:
                await activate(
                    "gpu-memory-warning",
                    "warning",
                    "GPU memory high",
                    f"GPU memory usage is at {usage_ratio * 100:.1f}%.",
                    metadata={"memory_used": memory_used, "memory_total": memory_total},
                )
            else:
                await deactivate(
                    "gpu-memory-warning",
                    "GPU memory usage nominal",
                    "GPU memory usage is within the safe range.",
                )

        performance_status = (performance.get("status") or "").lower()
        if performance_status == "critical":
            await activate(
                "gpu-performance-critical",
                "error",
                "GPU performance degraded",
                "Performance metrics indicate a critical slowdown.",
                metadata=performance,
            )
        else:
            await deactivate(
                "gpu-performance-critical",
                "GPU performance recovered",
                "Performance metrics are back within acceptable bounds.",
            )
        if performance_status == "warning":
            await activate(
                "gpu-performance-warning",
                "warning",
                "GPU performance warning",
                "GPU utilisation suggests potential throttling.",
                metadata=performance,
            )
        else:
            await deactivate(
                "gpu-performance-warning",
                "GPU performance nominal",
                "GPU utilisation returned to optimal values.",
            )

        cpu_percent = system.get("cpuPercent")
        if isinstance(cpu_percent, (int, float)) and cpu_percent >= self.thresholds.cpu_usage_warning:
            await activate(
                "cpu-overloaded",
                "warning",
                "CPU usage high",
                f"CPU utilisation reached {cpu_percent:.1f}%.",
                metadata={"cpuPercent": cpu_percent},
            )
        else:
            await deactivate(
                "cpu-overloaded",
                "CPU usage stabilised",
                "CPU utilisation dropped below 90%.",
            )

        memory_percent = system.get("memoryPercent")
        if isinstance(memory_percent, (int, float)) and memory_percent >= self.thresholds.ram_usage_warning:
            await activate(
                "ram-overloaded",
                "warning",
                "System memory low",
                f"RAM usage reached {memory_percent:.1f}%.",
                metadata={"memoryPercent": memory_percent},
            )
        else:
            await deactivate(
                "ram-overloaded",
                "System memory recovered",
                "RAM usage dropped below 90%.",
            )
