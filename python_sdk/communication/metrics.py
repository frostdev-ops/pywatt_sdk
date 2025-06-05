"""Performance Monitoring and Metrics for Communication Channels

This module provides comprehensive metrics collection, performance monitoring,
and health tracking for all communication channels. It supports real-time
monitoring, SLA tracking, and performance comparison between channels.
"""

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import logging
from datetime import datetime, timedelta
import uuid

from .tcp_channel import ChannelType

logger = logging.getLogger(__name__)


@dataclass
class PoolMetrics:
    """Connection pool metrics."""
    active_connections: int
    idle_connections: int
    max_pool_size: int
    total_connections_created: int
    total_connections_destroyed: int
    avg_connection_lifetime: float  # seconds


@dataclass
class ChannelMetrics:
    """Performance metrics for a communication channel."""
    channel_type: ChannelType
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    failures: int = 0
    successes: int = 0
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    throughput_mps: float = 0.0  # messages per second
    bandwidth_bps: float = 0.0   # bytes per second
    uptime: float = 0.0  # seconds
    last_updated: datetime = field(default_factory=datetime.now)
    availability: float = 1.0
    queue_depth: int = 0
    pool_stats: Optional[PoolMetrics] = None


@dataclass
class SlaConfig:
    """SLA (Service Level Agreement) configuration."""
    target_availability: float = 0.999  # 99.9%
    max_latency: float = 0.1  # 100ms
    target_throughput: float = 1000.0  # messages per second
    max_error_rate: float = 0.01  # 1%
    measurement_window: float = 3600.0  # 1 hour


@dataclass
class ComplianceStatus:
    """Compliance status for a specific metric."""
    current: float
    target: float
    compliant: bool
    difference_percent: float


@dataclass
class SlaStatus:
    """SLA compliance status."""
    compliant: bool
    availability_status: ComplianceStatus
    latency_status: ComplianceStatus
    throughput_status: ComplianceStatus
    error_rate_status: ComplianceStatus
    measurement_window: float
    calculated_at: datetime


@dataclass
class AlertConfig:
    """Performance alert configuration."""
    latency_threshold: float = 0.5  # 500ms
    error_rate_threshold: float = 0.05  # 5%
    throughput_drop_threshold: float = 0.5  # 50% drop
    availability_threshold: float = 0.95  # 95%
    min_alert_interval: float = 300.0  # 5 minutes


class AlertType(Enum):
    """Types of performance alerts."""
    HIGH_LATENCY = "high_latency"
    HIGH_ERROR_RATE = "high_error_rate"
    LOW_THROUGHPUT = "low_throughput"
    LOW_AVAILABILITY = "low_availability"
    CONNECTION_FAILURE = "connection_failure"
    QUEUE_BACKLOG = "queue_backlog"


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class PerformanceAlert:
    """Performance alert."""
    id: str
    channel_type: ChannelType
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    current_value: float
    threshold: float
    triggered_at: datetime
    active: bool = True


@dataclass
class LatencySample:
    """Latency measurement sample."""
    latency: float
    timestamp: datetime


@dataclass
class ThroughputSample:
    """Throughput measurement sample."""
    count: int
    bytes: int
    timestamp: datetime


class ChannelPerformanceTracker:
    """Channel performance tracker."""

    def __init__(
        self,
        channel_type: ChannelType,
        sla_config: SlaConfig,
        alert_config: AlertConfig,
    ):
        self.channel_type = channel_type
        self.sla_config = sla_config
        self.alert_config = alert_config
        self.metrics = ChannelMetrics(channel_type=channel_type)
        self.latency_samples: deque = deque(maxlen=1000)
        self.throughput_samples: deque = deque(maxlen=1000)
        self.connection_start_time = datetime.now()
        self.last_alert_times: Dict[AlertType, datetime] = {}
        self.sample_window = timedelta(minutes=5)
        self._lock = asyncio.Lock()

    def record_message_sent(self, bytes_count: int, latency: float) -> None:
        """Record a message sent."""
        self.metrics.messages_sent += 1
        self.metrics.bytes_sent += bytes_count
        self.metrics.successes += 1
        self.metrics.last_updated = datetime.now()
        self.metrics.uptime = (datetime.now() - self.connection_start_time).total_seconds()

        # Record latency sample
        self._record_latency(latency)

        # Update calculated metrics
        self._update_calculated_metrics()

    def record_message_received(self, bytes_count: int) -> None:
        """Record a message received."""
        self.metrics.messages_received += 1
        self.metrics.bytes_received += bytes_count
        self.metrics.last_updated = datetime.now()
        self.metrics.uptime = (datetime.now() - self.connection_start_time).total_seconds()

        # Update calculated metrics
        self._update_calculated_metrics()

    def record_failure(self) -> None:
        """Record a failed operation."""
        self.metrics.failures += 1
        self.metrics.last_updated = datetime.now()

        # Update error rate
        self._update_calculated_metrics()

        # Check for alerts
        self._check_error_rate_alert()

    def record_connection_state(self, connected: bool) -> None:
        """Record connection state change."""
        if connected:
            self.metrics.availability = 1.0
        else:
            self.metrics.availability = 0.0
            self.metrics.failures += 1

        self.metrics.last_updated = datetime.now()

        if not connected:
            self._trigger_alert(
                AlertType.CONNECTION_FAILURE,
                AlertSeverity.CRITICAL,
                "Channel connection lost",
                0.0,
                1.0,
            )

    def update_queue_depth(self, depth: int) -> None:
        """Update queue depth."""
        self.metrics.queue_depth = depth
        self.metrics.last_updated = datetime.now()

        # Check for queue backlog alert
        if depth > 1000:  # Configurable threshold
            self._trigger_alert(
                AlertType.QUEUE_BACKLOG,
                AlertSeverity.WARNING,
                f"High queue depth: {depth} messages",
                float(depth),
                1000.0,
            )

    def update_pool_stats(self, pool_stats: PoolMetrics) -> None:
        """Update pool statistics."""
        self.metrics.pool_stats = pool_stats
        self.metrics.last_updated = datetime.now()

    def get_metrics(self) -> ChannelMetrics:
        """Get current metrics snapshot."""
        return self.metrics

    def get_sla_status(self) -> SlaStatus:
        """Get SLA compliance status."""
        availability_status = ComplianceStatus(
            current=self.metrics.availability,
            target=self.sla_config.target_availability,
            compliant=self.metrics.availability >= self.sla_config.target_availability,
            difference_percent=((self.metrics.availability - self.sla_config.target_availability)
                               / self.sla_config.target_availability * 100.0),
        )

        latency_status = ComplianceStatus(
            current=self.metrics.p95_latency_ms,
            target=self.sla_config.max_latency * 1000,  # Convert to ms
            compliant=self.metrics.p95_latency_ms <= self.sla_config.max_latency * 1000,
            difference_percent=((self.metrics.p95_latency_ms - self.sla_config.max_latency * 1000)
                               / (self.sla_config.max_latency * 1000) * 100.0),
        )

        throughput_status = ComplianceStatus(
            current=self.metrics.throughput_mps,
            target=self.sla_config.target_throughput,
            compliant=self.metrics.throughput_mps >= self.sla_config.target_throughput,
            difference_percent=((self.metrics.throughput_mps - self.sla_config.target_throughput)
                               / self.sla_config.target_throughput * 100.0),
        )

        error_rate_status = ComplianceStatus(
            current=self.metrics.error_rate,
            target=self.sla_config.max_error_rate,
            compliant=self.metrics.error_rate <= self.sla_config.max_error_rate,
            difference_percent=((self.metrics.error_rate - self.sla_config.max_error_rate)
                               / self.sla_config.max_error_rate * 100.0),
        )

        compliant = (availability_status.compliant and
                    latency_status.compliant and
                    throughput_status.compliant and
                    error_rate_status.compliant)

        return SlaStatus(
            compliant=compliant,
            availability_status=availability_status,
            latency_status=latency_status,
            throughput_status=throughput_status,
            error_rate_status=error_rate_status,
            measurement_window=self.sla_config.measurement_window,
            calculated_at=datetime.now(),
        )

    def reset_metrics(self) -> None:
        """Reset metrics (useful for testing or periodic resets)."""
        self.metrics = ChannelMetrics(channel_type=self.channel_type)
        self.latency_samples.clear()
        self.throughput_samples.clear()

    def _record_latency(self, latency: float) -> None:
        """Record latency sample."""
        now = datetime.now()
        self.latency_samples.append(LatencySample(latency=latency, timestamp=now))

        # Remove old samples outside the window
        cutoff_time = now - self.sample_window
        while self.latency_samples and self.latency_samples[0].timestamp < cutoff_time:
            self.latency_samples.popleft()

        # Check for latency alert
        if latency > self.alert_config.latency_threshold:
            self._trigger_alert(
                AlertType.HIGH_LATENCY,
                AlertSeverity.WARNING,
                f"High latency detected: {latency * 1000:.1f}ms",
                latency * 1000,
                self.alert_config.latency_threshold * 1000,
            )

    def _update_calculated_metrics(self) -> None:
        """Update calculated metrics."""
        # Update error rate
        total_ops = self.metrics.successes + self.metrics.failures
        if total_ops > 0:
            self.metrics.error_rate = self.metrics.failures / total_ops

        # Update latency percentiles
        if self.latency_samples:
            latencies = [sample.latency for sample in self.latency_samples]
            latencies.sort()

            self.metrics.avg_latency_ms = sum(latencies) / len(latencies) * 1000

            # Calculate percentiles
            if latencies:
                p50_idx = int(len(latencies) * 0.5)
                p95_idx = int(len(latencies) * 0.95)
                p99_idx = int(len(latencies) * 0.99)

                self.metrics.p50_latency_ms = latencies[min(p50_idx, len(latencies) - 1)] * 1000
                self.metrics.p95_latency_ms = latencies[min(p95_idx, len(latencies) - 1)] * 1000
                self.metrics.p99_latency_ms = latencies[min(p99_idx, len(latencies) - 1)] * 1000
                self.metrics.max_latency_ms = max(latencies) * 1000

        # Update throughput (messages per second over last minute)
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)

        recent_messages = sum(
            1 for sample in self.throughput_samples
            if sample.timestamp >= one_minute_ago
        )
        self.metrics.throughput_mps = recent_messages / 60.0

        recent_bytes = sum(
            sample.bytes for sample in self.throughput_samples
            if sample.timestamp >= one_minute_ago
        )
        self.metrics.bandwidth_bps = recent_bytes / 60.0

    def _check_error_rate_alert(self) -> None:
        """Check if error rate exceeds threshold."""
        if self.metrics.error_rate > self.alert_config.error_rate_threshold:
            self._trigger_alert(
                AlertType.HIGH_ERROR_RATE,
                AlertSeverity.WARNING,
                f"High error rate: {self.metrics.error_rate * 100:.1f}%",
                self.metrics.error_rate * 100,
                self.alert_config.error_rate_threshold * 100,
            )

    def _trigger_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        current_value: float,
        threshold: float,
    ) -> None:
        """Trigger a performance alert."""
        now = datetime.now()

        # Check if we should suppress this alert due to minimum interval
        if alert_type in self.last_alert_times:
            time_since_last = now - self.last_alert_times[alert_type]
            if time_since_last.total_seconds() < self.alert_config.min_alert_interval:
                return

        self.last_alert_times[alert_type] = now

        alert = PerformanceAlert(
            id=str(uuid.uuid4()),
            channel_type=self.channel_type,
            alert_type=alert_type,
            severity=severity,
            message=message,
            current_value=current_value,
            threshold=threshold,
            triggered_at=now,
        )

        # Log the alert
        log_level = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.CRITICAL: logger.error,
        }[severity]

        log_level(f"Performance alert: {message} (channel: {self.channel_type.value})")


class PerformanceMonitoringSystem:
    """Performance monitoring system for all channels."""

    def __init__(self, sla_config: SlaConfig, alert_config: AlertConfig):
        self.sla_config = sla_config
        self.alert_config = alert_config
        self.trackers: Dict[ChannelType, ChannelPerformanceTracker] = {}
        self.monitoring_enabled = True
        self._lock = asyncio.Lock()

    def set_monitoring_enabled(self, enabled: bool) -> None:
        """Enable or disable monitoring."""
        self.monitoring_enabled = enabled

    async def get_tracker(self, channel_type: ChannelType) -> ChannelPerformanceTracker:
        """Get or create a performance tracker for a channel."""
        async with self._lock:
            if channel_type not in self.trackers:
                self.trackers[channel_type] = ChannelPerformanceTracker(
                    channel_type, self.sla_config, self.alert_config
                )
            return self.trackers[channel_type]

    async def get_all_metrics(self) -> Dict[ChannelType, ChannelMetrics]:
        """Get metrics for all channels."""
        async with self._lock:
            return {
                channel_type: tracker.get_metrics()
                for channel_type, tracker in self.trackers.items()
            }

    async def get_all_sla_status(self) -> Dict[ChannelType, SlaStatus]:
        """Get SLA status for all channels."""
        async with self._lock:
            return {
                channel_type: tracker.get_sla_status()
                for channel_type, tracker in self.trackers.items()
            }

    async def get_performance_comparison(self) -> 'PerformanceComparisonReport':
        """Get a performance comparison report across all channels."""
        metrics = await self.get_all_metrics()

        if not metrics:
            return PerformanceComparisonReport(
                metrics={},
                best_latency=None,
                best_throughput=None,
                best_availability=None,
                lowest_error_rate=None,
                generated_at=datetime.now(),
            )

        # Find best performing channels
        best_latency = min(
            ((ch, m.p95_latency_ms) for ch, m in metrics.items()),
            key=lambda x: x[1],
            default=None
        )

        best_throughput = max(
            ((ch, m.throughput_mps) for ch, m in metrics.items()),
            key=lambda x: x[1],
            default=None
        )

        best_availability = max(
            ((ch, m.availability) for ch, m in metrics.items()),
            key=lambda x: x[1],
            default=None
        )

        lowest_error_rate = min(
            ((ch, m.error_rate) for ch, m in metrics.items()),
            key=lambda x: x[1],
            default=None
        )

        return PerformanceComparisonReport(
            metrics=metrics,
            best_latency=best_latency,
            best_throughput=best_throughput,
            best_availability=best_availability,
            lowest_error_rate=lowest_error_rate,
            generated_at=datetime.now(),
        )

    async def reset_all_metrics(self) -> None:
        """Reset metrics for all channels."""
        async with self._lock:
            for tracker in self.trackers.values():
                tracker.reset_metrics()


@dataclass
class PerformanceComparisonReport:
    """Performance comparison report across channels."""
    metrics: Dict[ChannelType, ChannelMetrics]
    best_latency: Optional[tuple[ChannelType, float]]
    best_throughput: Optional[tuple[ChannelType, float]]
    best_availability: Optional[tuple[ChannelType, float]]
    lowest_error_rate: Optional[tuple[ChannelType, float]]
    generated_at: datetime 