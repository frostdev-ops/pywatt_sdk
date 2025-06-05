"""Smart Channel Routing Engine

This module provides intelligent routing decisions for message communication
between channels based on message characteristics, target location, and
performance metrics.
"""

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Dict, List, Optional, Tuple, Any, Callable, Awaitable
import logging
import weakref
from datetime import datetime, timedelta

from .message import EncodedMessage, MessageMetadata
from .tcp_channel import ChannelType

logger = logging.getLogger(__name__)


class MessagePriority(IntEnum):
    """Message priority levels for routing decisions."""
    CRITICAL = 3
    HIGH = 2
    NORMAL = 1
    LOW = 0
    BULK = -1


class MessageType(Enum):
    """Message types for routing decisions."""
    CONTROL = "control"
    DATA = "data"
    FILE_TRANSFER = "file_transfer"
    STREAM = "stream"
    REAL_TIME = "real_time"
    BATCH = "batch"


class TargetLocation(Enum):
    """Target location types for routing decisions."""
    LOCAL = "local"
    REMOTE = "remote"
    UNKNOWN = "unknown"


@dataclass
class MessageCharacteristics:
    """Message characteristics used for routing decisions."""
    size: int = 0
    priority: MessagePriority = MessagePriority.NORMAL
    message_type: MessageType = MessageType.DATA
    target_location: TargetLocation = TargetLocation.UNKNOWN
    requires_ack: bool = False
    timeout: Optional[float] = None
    retryable: bool = True


@dataclass
class RoutingCondition:
    """Conditions for applying routing preferences."""
    pass


@dataclass
class MaxSizeCondition(RoutingCondition):
    """Message size threshold condition."""
    max_size: int


@dataclass
class MinHealthCondition(RoutingCondition):
    """Minimum channel health threshold condition."""
    min_health: float


@dataclass
class MaxLatencyCondition(RoutingCondition):
    """Maximum latency requirement condition."""
    max_latency: float


@dataclass
class MinThroughputCondition(RoutingCondition):
    """Minimum throughput requirement condition."""
    min_throughput: int


@dataclass
class ChannelPreference:
    """Channel preference with priority and conditions."""
    primary: ChannelType
    fallback: Optional[ChannelType] = None
    conditions: List[RoutingCondition] = field(default_factory=list)
    weight: float = 1.0


@dataclass
class RoutingMatrix:
    """Routing matrix that defines channel preferences for different scenarios."""
    local_small_messages: ChannelPreference = field(default_factory=lambda: ChannelPreference(
        primary=ChannelType.IPC,
        fallback=ChannelType.TCP,
        conditions=[MaxSizeCondition(1024)],
        weight=1.0
    ))
    local_large_messages: ChannelPreference = field(default_factory=lambda: ChannelPreference(
        primary=ChannelType.TCP,
        fallback=ChannelType.IPC,
        conditions=[],
        weight=1.0
    ))
    remote_messages: ChannelPreference = field(default_factory=lambda: ChannelPreference(
        primary=ChannelType.TCP,
        fallback=None,
        conditions=[],
        weight=1.0
    ))
    urgent_messages: ChannelPreference = field(default_factory=lambda: ChannelPreference(
        primary=ChannelType.IPC,
        fallback=ChannelType.TCP,
        conditions=[MaxLatencyCondition(0.01)],  # 10ms
        weight=1.0
    ))
    bulk_transfer: ChannelPreference = field(default_factory=lambda: ChannelPreference(
        primary=ChannelType.TCP,
        fallback=None,
        conditions=[],
        weight=1.0
    ))
    real_time: ChannelPreference = field(default_factory=lambda: ChannelPreference(
        primary=ChannelType.IPC,
        fallback=ChannelType.TCP,
        conditions=[MaxLatencyCondition(0.005)],  # 5ms
        weight=1.0
    ))
    file_transfer: ChannelPreference = field(default_factory=lambda: ChannelPreference(
        primary=ChannelType.TCP,
        fallback=None,
        conditions=[],
        weight=1.0
    ))


@dataclass
class ChannelHealth:
    """Channel health and performance metrics."""
    latency_p95: float = 0.01  # 10ms default
    error_rate: float = 0.0
    throughput: int = 0
    availability: float = 1.0
    last_failure: Optional[datetime] = None
    connected: bool = True
    recent_latencies: deque = field(default_factory=lambda: deque(maxlen=100))
    recent_errors: int = 0
    recent_successes: int = 0
    last_update: datetime = field(default_factory=datetime.now)

    def record_success(self, latency: float) -> None:
        """Update health metrics with a successful operation."""
        self.recent_latencies.append(latency)
        self.recent_successes += 1
        self.last_update = datetime.now()
        self._update_metrics()

    def record_failure(self) -> None:
        """Update health metrics with a failed operation."""
        self.recent_errors += 1
        self.last_failure = datetime.now()
        self.last_update = datetime.now()
        self._update_metrics()

    def _update_metrics(self) -> None:
        """Update calculated metrics."""
        # Update latency percentile
        if self.recent_latencies:
            sorted_latencies = sorted(self.recent_latencies)
            p95_index = int(len(sorted_latencies) * 0.95)
            self.latency_p95 = sorted_latencies[p95_index] if p95_index < len(sorted_latencies) else sorted_latencies[-1]

        # Update error rate
        total_ops = self.recent_errors + self.recent_successes
        if total_ops > 0:
            self.error_rate = self.recent_errors / total_ops

        # Update availability based on recent failures
        if self.last_failure:
            time_since_failure = datetime.now() - self.last_failure
            if time_since_failure < timedelta(minutes=1):
                self.availability = 0.8  # Reduced availability after recent failure
            else:
                self.availability = 1.0 - self.error_rate
        else:
            self.availability = 1.0 - self.error_rate

        # Reset counters periodically
        if datetime.now() - self.last_update > timedelta(minutes=5):
            self.recent_errors = 0
            self.recent_successes = 0
            self.recent_latencies.clear()

    def meets_condition(self, condition: RoutingCondition) -> bool:
        """Check if the channel meets a specific condition."""
        if isinstance(condition, MinHealthCondition):
            return self.availability >= condition.min_health
        elif isinstance(condition, MaxLatencyCondition):
            return self.latency_p95 <= condition.max_latency
        elif isinstance(condition, MinThroughputCondition):
            return self.throughput >= condition.min_throughput
        elif isinstance(condition, MaxSizeCondition):
            return True  # Size conditions are checked against message, not channel
        return True


@dataclass
class RoutingCacheEntry:
    """Routing decision cache entry."""
    decision: 'RoutingDecision'
    cached_at: datetime
    hit_count: int = 0


@dataclass
class RoutingDecision:
    """The result of a routing decision."""
    primary_channel: ChannelType
    fallback_channel: Optional[ChannelType] = None
    confidence: float = 1.0
    reason: str = ""
    expected_latency: float = 0.01
    weight: float = 1.0


@dataclass
class RoutingConfig:
    """Configuration for the routing engine."""
    cache_ttl: float = 60.0  # seconds
    max_cache_size: int = 1000
    health_check_interval: float = 10.0  # seconds
    enable_load_balancing: bool = True
    learning_rate: float = 0.1


class ChannelRouter:
    """Smart channel routing engine."""

    def __init__(self, config: Optional[RoutingConfig] = None):
        self.config = config or RoutingConfig()
        self.routing_matrix = RoutingMatrix()
        self.channel_health: Dict[ChannelType, ChannelHealth] = {}
        self.decision_cache: Dict[str, RoutingCacheEntry] = {}
        self.load_balance_state: Dict[ChannelType, float] = defaultdict(float)
        self._lock = asyncio.Lock()

    def with_matrix(self, matrix: RoutingMatrix) -> 'ChannelRouter':
        """Create a new router with custom routing matrix."""
        self.routing_matrix = matrix
        return self

    async def route_message(
        self,
        message: EncodedMessage,
        target: str,
        characteristics: MessageCharacteristics,
        available_channels: List[ChannelType],
    ) -> Optional[RoutingDecision]:
        """Make a routing decision for a message."""
        # Generate cache key
        cache_key = f"{target}:{characteristics.priority}:{characteristics.message_type.value}:{characteristics.size}"

        # Check cache first
        cached_decision = self._get_cached_decision(cache_key)
        if cached_decision:
            logger.debug(f"Using cached routing decision for {target}")
            return cached_decision

        # Determine target location
        target_location = self._determine_target_location(target)
        characteristics.target_location = target_location

        # Get routing preference from matrix
        preference = await self._select_routing_preference(characteristics)

        # Filter available channels based on preference and health
        viable_channels = await self._filter_viable_channels(
            available_channels, preference, characteristics
        )

        if not viable_channels:
            logger.warning(f"No viable channels available for routing to {target}")
            return None

        # Apply load balancing if enabled
        if self.config.enable_load_balancing and len(viable_channels) > 1:
            selected = await self._select_with_load_balancing(viable_channels)
        else:
            selected = viable_channels[0]

        # Create routing decision
        health = await self._get_channel_health(selected)
        decision = RoutingDecision(
            primary_channel=selected,
            fallback_channel=viable_channels[1] if len(viable_channels) > 1 else None,
            confidence=self._calculate_confidence(preference, health, characteristics),
            reason=f"Selected {selected.value} based on {characteristics.priority.name.lower()} priority",
            expected_latency=health.latency_p95,
            weight=preference.weight,
        )

        # Cache the decision
        self._cache_decision(cache_key, decision)

        logger.debug(f"Routing decision for {target}: {decision.reason} (confidence: {decision.confidence:.2f})")
        return decision

    async def record_outcome(
        self,
        channel: ChannelType,
        success: bool,
        latency: Optional[float] = None,
    ) -> None:
        """Record the outcome of a routing decision for learning."""
        async with self._lock:
            if channel not in self.channel_health:
                self.channel_health[channel] = ChannelHealth()

            health = self.channel_health[channel]
            if success:
                health.record_success(latency or 0.01)
            else:
                health.record_failure()

            # Adaptive learning: update routing weights based on outcomes
            await self._update_routing_weights(channel, success)

    async def update_channel_status(self, channel: ChannelType, connected: bool) -> None:
        """Update the connection status of a channel."""
        async with self._lock:
            if channel not in self.channel_health:
                self.channel_health[channel] = ChannelHealth()
            self.channel_health[channel].connected = connected

    async def get_health_status(self) -> Dict[ChannelType, ChannelHealth]:
        """Get health status for all channels."""
        async with self._lock:
            return self.channel_health.copy()

    def update_routing_matrix(self, matrix: RoutingMatrix) -> None:
        """Update the routing matrix."""
        self.routing_matrix = matrix
        # Clear cache when matrix changes
        self.decision_cache.clear()

    def get_routing_matrix(self) -> RoutingMatrix:
        """Get the current routing matrix."""
        return self.routing_matrix

    def _determine_target_location(self, target: str) -> TargetLocation:
        """Determine if target is local or remote."""
        if target.startswith("127.0.0.1") or target.startswith("localhost") or target.startswith("unix:"):
            return TargetLocation.LOCAL
        elif ":" in target and not target.startswith("unix:"):
            return TargetLocation.REMOTE
        else:
            return TargetLocation.UNKNOWN

    async def _select_routing_preference(self, characteristics: MessageCharacteristics) -> ChannelPreference:
        """Select routing preference based on message characteristics."""
        if characteristics.priority in (MessagePriority.CRITICAL, MessagePriority.HIGH):
            return self.routing_matrix.urgent_messages
        elif characteristics.message_type == MessageType.FILE_TRANSFER:
            return self.routing_matrix.file_transfer
        elif characteristics.message_type == MessageType.REAL_TIME:
            return self.routing_matrix.real_time
        elif characteristics.message_type == MessageType.BATCH or characteristics.priority == MessagePriority.BULK:
            return self.routing_matrix.bulk_transfer
        elif characteristics.target_location == TargetLocation.REMOTE:
            return self.routing_matrix.remote_messages
        elif characteristics.size < 1024:  # Small messages
            return self.routing_matrix.local_small_messages
        else:  # Large messages
            return self.routing_matrix.local_large_messages

    async def _filter_viable_channels(
        self,
        available_channels: List[ChannelType],
        preference: ChannelPreference,
        characteristics: MessageCharacteristics,
    ) -> List[ChannelType]:
        """Filter available channels based on preference and health."""
        viable = []

        # Check primary channel first
        if preference.primary in available_channels:
            health = await self._get_channel_health(preference.primary)
            if health.connected and self._channel_meets_conditions(health, preference.conditions, characteristics):
                viable.append(preference.primary)

        # Check fallback channel
        if preference.fallback and preference.fallback in available_channels:
            health = await self._get_channel_health(preference.fallback)
            if health.connected and self._channel_meets_conditions(health, preference.conditions, characteristics):
                if preference.fallback not in viable:
                    viable.append(preference.fallback)

        # Add other available channels as last resort
        for channel in available_channels:
            if channel not in viable:
                health = await self._get_channel_health(channel)
                if health.connected:
                    viable.append(channel)

        return viable

    def _channel_meets_conditions(
        self,
        health: ChannelHealth,
        conditions: List[RoutingCondition],
        characteristics: MessageCharacteristics,
    ) -> bool:
        """Check if channel meets all conditions."""
        for condition in conditions:
            if isinstance(condition, MaxSizeCondition):
                if characteristics.size > condition.max_size:
                    return False
            elif not health.meets_condition(condition):
                return False
        return True

    async def _select_with_load_balancing(self, channels: List[ChannelType]) -> ChannelType:
        """Select channel using load balancing."""
        if not channels:
            raise ValueError("No channels available for load balancing")

        # Simple round-robin load balancing
        # In a real implementation, you might use weighted round-robin or least connections
        async with self._lock:
            # Find channel with lowest load
            min_load = min(self.load_balance_state[ch] for ch in channels)
            candidates = [ch for ch in channels if self.load_balance_state[ch] == min_load]

            # Select first candidate and increment its load
            selected = candidates[0]
            self.load_balance_state[selected] += 1.0

            return selected

    async def _get_channel_health(self, channel: ChannelType) -> ChannelHealth:
        """Get health metrics for a channel."""
        async with self._lock:
            if channel not in self.channel_health:
                self.channel_health[channel] = ChannelHealth()
            return self.channel_health[channel]

    def _calculate_confidence(
        self,
        preference: ChannelPreference,
        health: ChannelHealth,
        characteristics: MessageCharacteristics,
    ) -> float:
        """Calculate confidence in the routing decision."""
        confidence = 1.0

        # Reduce confidence based on error rate
        confidence *= (1.0 - health.error_rate)

        # Reduce confidence based on availability
        confidence *= health.availability

        # Reduce confidence if latency is high
        if health.latency_p95 > 0.1:  # 100ms
            confidence *= 0.8

        # Increase confidence if this is the preferred channel
        if characteristics.priority in (MessagePriority.CRITICAL, MessagePriority.HIGH):
            confidence *= 1.1

        return min(confidence, 1.0)

    def _get_cached_decision(self, cache_key: str) -> Optional[RoutingDecision]:
        """Get a cached routing decision if still valid."""
        if cache_key in self.decision_cache:
            entry = self.decision_cache[cache_key]
            if datetime.now() - entry.cached_at < timedelta(seconds=self.config.cache_ttl):
                entry.hit_count += 1
                return entry.decision
            else:
                del self.decision_cache[cache_key]
        return None

    def _cache_decision(self, cache_key: str, decision: RoutingDecision) -> None:
        """Cache a routing decision."""
        # Limit cache size
        if len(self.decision_cache) >= self.config.max_cache_size:
            # Remove oldest entries
            oldest_keys = sorted(
                self.decision_cache.keys(),
                key=lambda k: self.decision_cache[k].cached_at
            )[:self.config.max_cache_size // 4]
            for key in oldest_keys:
                del self.decision_cache[key]

        self.decision_cache[cache_key] = RoutingCacheEntry(
            decision=decision,
            cached_at=datetime.now(),
            hit_count=0
        )

    async def _update_routing_weights(self, channel: ChannelType, success: bool) -> None:
        """Update routing weights based on outcomes (adaptive learning)."""
        # Simple adaptive learning: adjust load balancing weights
        if success:
            # Slightly reduce load for successful channels
            self.load_balance_state[channel] = max(0, self.load_balance_state[channel] - self.config.learning_rate)
        else:
            # Increase load for failed channels (making them less likely to be selected)
            self.load_balance_state[channel] += self.config.learning_rate * 2


def extract_message_characteristics(
    message: EncodedMessage,
    metadata: Optional[MessageMetadata] = None,
    target: str = "",
) -> MessageCharacteristics:
    """Extract message characteristics for routing decisions."""
    characteristics = MessageCharacteristics()

    # Extract size
    characteristics.size = len(message.data)

    # Extract priority from metadata if available
    if metadata and hasattr(metadata, 'priority'):
        try:
            characteristics.priority = MessagePriority(metadata.priority)
        except (ValueError, TypeError):
            characteristics.priority = MessagePriority.NORMAL

    # Infer message type based on size and metadata
    if characteristics.size > 1024 * 1024:  # 1MB
        characteristics.message_type = MessageType.FILE_TRANSFER
    elif characteristics.size < 256:  # Small control messages
        characteristics.message_type = MessageType.CONTROL
    elif metadata and hasattr(metadata, 'content_type'):
        if 'stream' in metadata.content_type.lower():
            characteristics.message_type = MessageType.STREAM
        elif 'batch' in metadata.content_type.lower():
            characteristics.message_type = MessageType.BATCH
        elif 'realtime' in metadata.content_type.lower():
            characteristics.message_type = MessageType.REAL_TIME
        else:
            characteristics.message_type = MessageType.DATA
    else:
        characteristics.message_type = MessageType.DATA

    # Extract timeout from metadata
    if metadata and hasattr(metadata, 'timeout'):
        characteristics.timeout = metadata.timeout

    # Extract other properties
    if metadata:
        if hasattr(metadata, 'requires_ack'):
            characteristics.requires_ack = metadata.requires_ack
        if hasattr(metadata, 'retryable'):
            characteristics.retryable = metadata.retryable

    return characteristics 