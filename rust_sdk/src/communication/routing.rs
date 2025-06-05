//! Smart Channel Routing Engine
//!
//! This module provides intelligent routing decisions for message communication
//! between channels based on message characteristics, target location, and
//! performance metrics.

use crate::communication::ChannelType;
use crate::message::{EncodedMessage, MessageMetadata};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant};
use std::sync::{Arc, RwLock};
use tokio::sync::RwLock as AsyncRwLock;
use tracing::{debug, warn, info};

/// Message priority levels for routing decisions
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MessagePriority {
    /// Critical messages that need immediate delivery
    Critical,
    /// High priority messages for important operations
    High,
    /// Normal priority messages for standard operations
    Normal,
    /// Low priority messages for background tasks
    Low,
    /// Bulk transfer operations
    Bulk,
}

impl Default for MessagePriority {
    fn default() -> Self {
        Self::Normal
    }
}

/// Message types for routing decisions
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MessageType {
    /// Small control messages
    Control,
    /// Medium-sized data messages
    Data,
    /// Large file transfers
    FileTransfer,
    /// Streaming data
    Stream,
    /// Real-time communication
    RealTime,
    /// Batch processing
    Batch,
}

impl Default for MessageType {
    fn default() -> Self {
        Self::Data
    }
}

/// Target location types for routing decisions
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TargetLocation {
    /// Local same-host communication
    Local,
    /// Remote cross-host communication
    Remote,
    /// Unknown or undetermined location
    Unknown,
}

/// Message characteristics used for routing decisions
#[derive(Debug, Clone)]
pub struct MessageCharacteristics {
    /// Size of the message in bytes
    pub size: usize,
    /// Priority level of the message
    pub priority: MessagePriority,
    /// Type of the message
    pub message_type: MessageType,
    /// Target location
    pub target_location: TargetLocation,
    /// Whether message requires acknowledgment
    pub requires_ack: bool,
    /// Expected response time requirements
    pub timeout: Option<Duration>,
    /// Whether message can be retried
    pub retryable: bool,
}

impl Default for MessageCharacteristics {
    fn default() -> Self {
        Self {
            size: 0,
            priority: MessagePriority::Normal,
            message_type: MessageType::Data,
            target_location: TargetLocation::Unknown,
            requires_ack: false,
            timeout: None,
            retryable: true,
        }
    }
}

/// Routing matrix that defines channel preferences for different scenarios
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoutingMatrix {
    /// Preference for local small messages
    pub local_small_messages: ChannelPreference,
    /// Preference for local large messages
    pub local_large_messages: ChannelPreference,
    /// Preference for remote messages
    pub remote_messages: ChannelPreference,
    /// Preference for urgent/critical messages
    pub urgent_messages: ChannelPreference,
    /// Preference for bulk transfer operations
    pub bulk_transfer: ChannelPreference,
    /// Preference for real-time communication
    pub real_time: ChannelPreference,
    /// Preference for file transfers
    pub file_transfer: ChannelPreference,
}

/// Channel preference with priority and conditions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChannelPreference {
    /// Primary preferred channel
    pub primary: ChannelType,
    /// Secondary fallback channel
    pub fallback: Option<ChannelType>,
    /// Conditions that must be met to use this preference
    pub conditions: Vec<RoutingCondition>,
    /// Weight for load balancing (0.0 to 1.0)
    pub weight: f64,
}

/// Conditions for applying routing preferences
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum RoutingCondition {
    /// Message size threshold
    MaxSize(usize),
    /// Minimum channel health threshold
    MinHealth(f64),
    /// Maximum latency requirement
    MaxLatency(Duration),
    /// Minimum throughput requirement
    MinThroughput(u64),
}

impl Default for RoutingMatrix {
    fn default() -> Self {
        Self {
            local_small_messages: ChannelPreference {
                primary: ChannelType::Ipc,
                fallback: Some(ChannelType::Tcp),
                conditions: vec![RoutingCondition::MaxSize(1024)],
                weight: 1.0,
            },
            local_large_messages: ChannelPreference {
                primary: ChannelType::Tcp,
                fallback: Some(ChannelType::Ipc),
                conditions: vec![],
                weight: 1.0,
            },
            remote_messages: ChannelPreference {
                primary: ChannelType::Tcp,
                fallback: None,
                conditions: vec![],
                weight: 1.0,
            },
            urgent_messages: ChannelPreference {
                primary: ChannelType::Ipc,
                fallback: Some(ChannelType::Tcp),
                conditions: vec![RoutingCondition::MaxLatency(Duration::from_millis(10))],
                weight: 1.0,
            },
            bulk_transfer: ChannelPreference {
                primary: ChannelType::Tcp,
                fallback: None,
                conditions: vec![],
                weight: 1.0,
            },
            real_time: ChannelPreference {
                primary: ChannelType::Ipc,
                fallback: Some(ChannelType::Tcp),
                conditions: vec![RoutingCondition::MaxLatency(Duration::from_millis(5))],
                weight: 1.0,
            },
            file_transfer: ChannelPreference {
                primary: ChannelType::Tcp,
                fallback: None,
                conditions: vec![],
                weight: 1.0,
            },
        }
    }
}

/// Channel health and performance metrics
#[derive(Debug, Clone)]
pub struct ChannelHealth {
    /// 95th percentile latency
    pub latency_p95: Duration,
    /// Error rate (0.0 to 1.0)
    pub error_rate: f64,
    /// Messages per second throughput
    pub throughput: u64,
    /// Availability (0.0 to 1.0)
    pub availability: f64,
    /// Last time a failure occurred
    pub last_failure: Option<Instant>,
    /// Current connection state
    pub connected: bool,
    /// Recent latency samples for calculation
    recent_latencies: Vec<Duration>,
    /// Recent error count
    recent_errors: u64,
    /// Recent success count
    recent_successes: u64,
    /// Last update time
    last_update: Instant,
}

impl Default for ChannelHealth {
    fn default() -> Self {
        Self {
            latency_p95: Duration::from_millis(10),
            error_rate: 0.0,
            throughput: 0,
            availability: 1.0,
            last_failure: None,
            connected: true,
            recent_latencies: Vec::new(),
            recent_errors: 0,
            recent_successes: 0,
            last_update: Instant::now(),
        }
    }
}

impl ChannelHealth {
    /// Update health metrics with a successful operation
    pub fn record_success(&mut self, latency: Duration) {
        self.recent_latencies.push(latency);
        self.recent_successes += 1;
        self.last_update = Instant::now();
        
        // Keep only recent samples (last 100)
        if self.recent_latencies.len() > 100 {
            self.recent_latencies.drain(0..10);
        }
        
        self.update_metrics();
    }
    
    /// Update health metrics with a failed operation
    pub fn record_failure(&mut self) {
        self.recent_errors += 1;
        self.last_failure = Some(Instant::now());
        self.last_update = Instant::now();
        self.update_metrics();
    }
    
    /// Update calculated metrics
    fn update_metrics(&mut self) {
        // Update latency percentile
        if !self.recent_latencies.is_empty() {
            let mut sorted = self.recent_latencies.clone();
            sorted.sort();
            let p95_index = (sorted.len() as f64 * 0.95) as usize;
            self.latency_p95 = sorted.get(p95_index).copied().unwrap_or(Duration::ZERO);
        }
        
        // Update error rate
        let total_ops = self.recent_errors + self.recent_successes;
        if total_ops > 0 {
            self.error_rate = self.recent_errors as f64 / total_ops as f64;
        }
        
        // Update availability based on recent failures
        if let Some(last_failure) = self.last_failure {
            let time_since_failure = last_failure.elapsed();
            if time_since_failure < Duration::from_secs(60) {
                self.availability = 0.8; // Reduced availability after recent failure
            } else {
                self.availability = 1.0 - self.error_rate;
            }
        } else {
            self.availability = 1.0 - self.error_rate;
        }
        
        // Reset counters periodically
        if self.last_update.elapsed() > Duration::from_secs(300) { // 5 minutes
            self.recent_errors = 0;
            self.recent_successes = 0;
            self.recent_latencies.clear();
        }
    }
    
    /// Check if the channel meets a specific condition
    pub fn meets_condition(&self, condition: &RoutingCondition) -> bool {
        match condition {
            RoutingCondition::MinHealth(threshold) => self.availability >= *threshold,
            RoutingCondition::MaxLatency(max_latency) => self.latency_p95 <= *max_latency,
            RoutingCondition::MinThroughput(min_throughput) => self.throughput >= *min_throughput,
            RoutingCondition::MaxSize(_) => true, // Size conditions are checked against message, not channel
        }
    }
}

/// Routing decision cache entry
#[derive(Debug, Clone)]
struct RoutingCacheEntry {
    /// The routing decision
    decision: RoutingDecision,
    /// When this decision was cached
    cached_at: Instant,
    /// How many times this decision was used
    hit_count: u64,
}

/// The result of a routing decision
#[derive(Debug, Clone)]
pub struct RoutingDecision {
    /// Primary channel to use
    pub primary_channel: ChannelType,
    /// Fallback channel if primary fails
    pub fallback_channel: Option<ChannelType>,
    /// Confidence in this decision (0.0 to 1.0)
    pub confidence: f64,
    /// Reason for this decision
    pub reason: String,
    /// Expected latency for this route
    pub expected_latency: Duration,
    /// Load balancing weight
    pub weight: f64,
}

/// Smart channel routing engine
pub struct ChannelRouter {
    /// Current routing matrix
    routing_matrix: Arc<RwLock<RoutingMatrix>>,
    /// Channel health metrics
    channel_health: Arc<AsyncRwLock<HashMap<ChannelType, ChannelHealth>>>,
    /// Routing decision cache
    decision_cache: Arc<RwLock<HashMap<String, RoutingCacheEntry>>>,
    /// Load balancing state
    load_balance_state: Arc<RwLock<HashMap<ChannelType, f64>>>,
    /// Configuration
    config: RoutingConfig,
}

/// Configuration for the routing engine
#[derive(Debug, Clone)]
pub struct RoutingConfig {
    /// Cache TTL for routing decisions
    pub cache_ttl: Duration,
    /// Maximum cache size
    pub max_cache_size: usize,
    /// Health check interval
    pub health_check_interval: Duration,
    /// Enable load balancing
    pub enable_load_balancing: bool,
    /// Learning rate for adaptive routing
    pub learning_rate: f64,
}

impl Default for RoutingConfig {
    fn default() -> Self {
        Self {
            cache_ttl: Duration::from_secs(60),
            max_cache_size: 1000,
            health_check_interval: Duration::from_secs(10),
            enable_load_balancing: true,
            learning_rate: 0.1,
        }
    }
}

impl ChannelRouter {
    /// Create a new channel router
    pub fn new(config: RoutingConfig) -> Self {
        Self {
            routing_matrix: Arc::new(RwLock::new(RoutingMatrix::default())),
            channel_health: Arc::new(AsyncRwLock::new(HashMap::new())),
            decision_cache: Arc::new(RwLock::new(HashMap::new())),
            load_balance_state: Arc::new(RwLock::new(HashMap::new())),
            config,
        }
    }
    
    /// Create a new router with custom routing matrix
    pub fn with_matrix(matrix: RoutingMatrix, config: RoutingConfig) -> Self {
        Self {
            routing_matrix: Arc::new(RwLock::new(matrix)),
            channel_health: Arc::new(AsyncRwLock::new(HashMap::new())),
            decision_cache: Arc::new(RwLock::new(HashMap::new())),
            load_balance_state: Arc::new(RwLock::new(HashMap::new())),
            config,
        }
    }
    
    /// Make a routing decision for a message
    pub async fn route_message(
        &self,
        message: &EncodedMessage,
        target: &str,
        characteristics: MessageCharacteristics,
        available_channels: &[ChannelType],
    ) -> Option<RoutingDecision> {
        // Generate cache key
        let cache_key = format!("{}:{}:{}:{}", 
            target, characteristics.priority as u8, 
            characteristics.message_type as u8, characteristics.size);
        
        // Check cache first
        if let Some(cached) = self.get_cached_decision(&cache_key) {
            debug!("Using cached routing decision for {}", target);
            return Some(cached);
        }
        
        // Determine target location
        let target_location = self.determine_target_location(target);
        let mut characteristics = characteristics;
        characteristics.target_location = target_location;
        
        // Get routing preference from matrix
        let preference = self.select_routing_preference(&characteristics).await;
        
        // Filter available channels based on preference and health
        let viable_channels = self.filter_viable_channels(
            available_channels, 
            &preference, 
            &characteristics
        ).await;
        
        if viable_channels.is_empty() {
            warn!("No viable channels available for routing to {}", target);
            return None;
        }
        
        // Apply load balancing if enabled
        let selected = if self.config.enable_load_balancing && viable_channels.len() > 1 {
            self.select_with_load_balancing(&viable_channels).await
        } else {
            viable_channels[0]
        };
        
        // Create routing decision
        let health = self.get_channel_health(selected).await;
        let decision = RoutingDecision {
            primary_channel: selected,
            fallback_channel: viable_channels.get(1).copied(),
            confidence: self.calculate_confidence(&preference, &health, &characteristics),
            reason: format!("Selected {} based on {} preference", 
                match selected {
                    ChannelType::Tcp => "TCP",
                    ChannelType::Ipc => "IPC",
                },
                match characteristics.priority {
                    MessagePriority::Critical => "critical priority",
                    MessagePriority::High => "high priority", 
                    MessagePriority::Normal => "normal routing",
                    MessagePriority::Low => "low priority",
                    MessagePriority::Bulk => "bulk transfer",
                }
            ),
            expected_latency: health.latency_p95,
            weight: preference.weight,
        };
        
        // Cache the decision
        self.cache_decision(cache_key, decision.clone());
        
        debug!("Routing decision for {}: {} (confidence: {:.2})", 
            target, decision.reason, decision.confidence);
        
        Some(decision)
    }
    
    /// Record the outcome of a routing decision for learning
    pub async fn record_outcome(
        &self,
        channel: ChannelType,
        success: bool,
        latency: Option<Duration>,
    ) {
        let mut health_map = self.channel_health.write().await;
        let health = health_map.entry(channel).or_insert_with(ChannelHealth::default);
        
        if success {
            if let Some(latency) = latency {
                health.record_success(latency);
            } else {
                health.record_success(Duration::from_millis(10)); // Default success latency
            }
        } else {
            health.record_failure();
        }
        
        // Adaptive learning: update routing matrix based on outcomes
        if self.config.learning_rate > 0.0 {
            self.update_routing_weights(channel, success).await;
        }
    }
    
    /// Update channel connection status
    pub async fn update_channel_status(&self, channel: ChannelType, connected: bool) {
        let mut health_map = self.channel_health.write().await;
        let health = health_map.entry(channel).or_insert_with(ChannelHealth::default);
        health.connected = connected;
        
        if !connected {
            health.record_failure();
        }
    }
    
    /// Get current health status for all channels
    pub async fn get_health_status(&self) -> HashMap<ChannelType, ChannelHealth> {
        self.channel_health.read().await.clone()
    }
    
    /// Update the routing matrix
    pub fn update_routing_matrix(&self, matrix: RoutingMatrix) {
        if let Ok(mut current_matrix) = self.routing_matrix.write() {
            *current_matrix = matrix;
            
            // Clear cache when matrix changes
            if let Ok(mut cache) = self.decision_cache.write() {
                cache.clear();
            }
            
            info!("Routing matrix updated");
        }
    }
    
    /// Get the current routing matrix
    pub fn get_routing_matrix(&self) -> RoutingMatrix {
        self.routing_matrix.read().unwrap().clone()
    }
    
    // Private helper methods
    
    fn determine_target_location(&self, target: &str) -> TargetLocation {
        if target.starts_with("127.0.0.1") || 
           target.starts_with("localhost") ||
           target.starts_with("unix://") ||
           !target.contains(':') {
            TargetLocation::Local
        } else {
            TargetLocation::Remote
        }
    }
    
    async fn select_routing_preference(&self, characteristics: &MessageCharacteristics) -> ChannelPreference {
        let matrix = self.routing_matrix.read().unwrap().clone();
        
        match (characteristics.target_location, characteristics.priority, characteristics.message_type) {
            (_, MessagePriority::Critical, _) => matrix.urgent_messages,
            (_, MessagePriority::High, MessageType::RealTime) => matrix.real_time,
            (_, MessagePriority::Bulk, _) => matrix.bulk_transfer,
            (_, _, MessageType::FileTransfer) => matrix.file_transfer,
            (TargetLocation::Local, _, _) if characteristics.size < 1024 => matrix.local_small_messages,
            (TargetLocation::Local, _, _) => matrix.local_large_messages,
            (TargetLocation::Remote, _, _) => matrix.remote_messages,
            _ => matrix.local_small_messages, // Default fallback
        }
    }
    
    async fn filter_viable_channels(
        &self,
        available_channels: &[ChannelType],
        preference: &ChannelPreference,
        characteristics: &MessageCharacteristics,
    ) -> Vec<ChannelType> {
        let health_map = self.channel_health.read().await;
        let mut viable = Vec::new();
        
        // Check primary channel first
        if available_channels.contains(&preference.primary) {
            if let Some(health) = health_map.get(&preference.primary) {
                if health.connected && self.channel_meets_conditions(health, &preference.conditions, characteristics) {
                    viable.push(preference.primary);
                }
            } else {
                // No health data yet, assume it's viable
                viable.push(preference.primary);
            }
        }
        
        // Check fallback channel
        if let Some(fallback) = preference.fallback {
            if available_channels.contains(&fallback) && !viable.contains(&fallback) {
                if let Some(health) = health_map.get(&fallback) {
                    if health.connected && self.channel_meets_conditions(health, &preference.conditions, characteristics) {
                        viable.push(fallback);
                    }
                } else {
                    viable.push(fallback);
                }
            }
        }
        
        // Add any other available channels as last resort
        for &channel in available_channels {
            if !viable.contains(&channel) {
                if let Some(health) = health_map.get(&channel) {
                    if health.connected {
                        viable.push(channel);
                    }
                } else {
                    viable.push(channel);
                }
            }
        }
        
        viable
    }
    
    fn channel_meets_conditions(
        &self,
        health: &ChannelHealth,
        conditions: &[RoutingCondition],
        characteristics: &MessageCharacteristics,
    ) -> bool {
        for condition in conditions {
            match condition {
                RoutingCondition::MaxSize(max_size) => {
                    if characteristics.size > *max_size {
                        return false;
                    }
                }
                _ => {
                    if !health.meets_condition(condition) {
                        return false;
                    }
                }
            }
        }
        true
    }
    
    async fn select_with_load_balancing(&self, channels: &[ChannelType]) -> ChannelType {
        let mut load_state = self.load_balance_state.write().unwrap();
        
        // Simple weighted round-robin
        let mut best_channel = channels[0];
        let mut best_weight = f64::INFINITY;
        
        for &channel in channels {
            let current_weight = load_state.get(&channel).copied().unwrap_or(0.0);
            if current_weight < best_weight {
                best_weight = current_weight;
                best_channel = channel;
            }
        }
        
        // Update weight
        let new_weight = best_weight + 1.0;
        load_state.insert(best_channel, new_weight);
        
        // Reset weights periodically
        if load_state.values().any(|&w| w > 1000.0) {
            for weight in load_state.values_mut() {
                *weight = 0.0;
            }
        }
        
        best_channel
    }
    
    async fn get_channel_health(&self, channel: ChannelType) -> ChannelHealth {
        self.channel_health.read().await
            .get(&channel)
            .cloned()
            .unwrap_or_default()
    }
    
    fn calculate_confidence(
        &self,
        preference: &ChannelPreference,
        health: &ChannelHealth,
        characteristics: &MessageCharacteristics,
    ) -> f64 {
        let mut confidence = 0.8; // Base confidence
        
        // Adjust based on health
        confidence *= health.availability;
        
        // Adjust based on latency requirements
        if let Some(timeout) = characteristics.timeout {
            if health.latency_p95 < timeout / 2 {
                confidence += 0.1;
            } else if health.latency_p95 > timeout {
                confidence -= 0.3;
            }
        }
        
        // Adjust based on error rate
        confidence *= 1.0 - health.error_rate;
        
        confidence.max(0.0).min(1.0)
    }
    
    fn get_cached_decision(&self, cache_key: &str) -> Option<RoutingDecision> {
        if let Ok(cache) = self.decision_cache.read() {
            if let Some(entry) = cache.get(cache_key) {
                if entry.cached_at.elapsed() < self.config.cache_ttl {
                    return Some(entry.decision.clone());
                }
            }
        }
        None
    }
    
    fn cache_decision(&self, cache_key: String, decision: RoutingDecision) {
        if let Ok(mut cache) = self.decision_cache.write() {
            // Evict old entries if cache is full
            if cache.len() >= self.config.max_cache_size {
                let oldest_key = cache.iter()
                    .min_by_key(|(_, entry)| entry.cached_at)
                    .map(|(key, _)| key.clone());
                
                if let Some(key) = oldest_key {
                    cache.remove(&key);
                }
            }
            
            cache.insert(cache_key, RoutingCacheEntry {
                decision,
                cached_at: Instant::now(),
                hit_count: 0,
            });
        }
    }
    
    async fn update_routing_weights(&self, channel: ChannelType, success: bool) {
        // Simple learning algorithm: increase weight for successful channels
        let adjustment = if success { 
            self.config.learning_rate 
        } else { 
            -self.config.learning_rate * 2.0 
        };
        
        if let Ok(mut matrix) = self.routing_matrix.write() {
            // Update weights in routing matrix based on performance
            let mut updated = false;
            
            macro_rules! update_preference {
                ($pref:expr) => {
                    if $pref.primary == channel || $pref.fallback == Some(channel) {
                        $pref.weight = ($pref.weight + adjustment).max(0.1).min(2.0);
                        updated = true;
                    }
                };
            }
            
            update_preference!(matrix.local_small_messages);
            update_preference!(matrix.local_large_messages);
            update_preference!(matrix.remote_messages);
            update_preference!(matrix.urgent_messages);
            update_preference!(matrix.bulk_transfer);
            update_preference!(matrix.real_time);
            update_preference!(matrix.file_transfer);
            
            if updated {
                debug!("Updated routing weights for {:?} (success: {})", channel, success);
            }
        }
    }
}

/// Extract message characteristics from an encoded message
pub fn extract_message_characteristics(
    message: &EncodedMessage,
    metadata: Option<&MessageMetadata>,
    target: &str,
) -> MessageCharacteristics {
    let size = message.data().len();
    let target_location = if target.starts_with("127.0.0.1") || 
                            target.starts_with("localhost") ||
                            target.starts_with("unix://") ||
                            !target.contains(':') {
        TargetLocation::Local
    } else {
        TargetLocation::Remote
    };
    
    // Extract priority and type from metadata if available
    let (priority, message_type) = if let Some(meta) = metadata {
        let priority = meta.properties.as_ref()
            .and_then(|props| props.get("priority"))
            .and_then(|p| p.as_str())
            .and_then(|s| match s {
                "critical" => Some(MessagePriority::Critical),
                "high" => Some(MessagePriority::High),
                "normal" => Some(MessagePriority::Normal),
                "low" => Some(MessagePriority::Low),
                "bulk" => Some(MessagePriority::Bulk),
                _ => None,
            })
            .unwrap_or(MessagePriority::Normal);
            
        let msg_type = meta.properties.as_ref()
            .and_then(|props| props.get("type"))
            .and_then(|t| t.as_str())
            .and_then(|s| match s {
                "control" => Some(MessageType::Control),
                "data" => Some(MessageType::Data),
                "file_transfer" => Some(MessageType::FileTransfer),
                "stream" => Some(MessageType::Stream),
                "real_time" => Some(MessageType::RealTime),
                "batch" => Some(MessageType::Batch),
                _ => None,
            })
            .unwrap_or(MessageType::Data);
            
        (priority, msg_type)
    } else {
        // Infer characteristics from message size and target
        let inferred_type = if size > 1024 * 1024 { // > 1MB
            MessageType::FileTransfer
        } else if size < 100 {
            MessageType::Control
        } else {
            MessageType::Data
        };
        
        (MessagePriority::Normal, inferred_type)
    };
    
    MessageCharacteristics {
        size,
        priority,
        message_type,
        target_location,
        requires_ack: metadata.map_or(false, |m| {
            m.properties.as_ref()
                .and_then(|props| props.get("requires_ack"))
                .and_then(|v| v.as_bool())
                .unwrap_or(false)
        }),
        timeout: metadata
            .and_then(|m| m.properties.as_ref())
            .and_then(|props| props.get("timeout"))
            .and_then(|v| v.as_u64())
            .map(Duration::from_millis),
        retryable: metadata.map_or(true, |m| {
            m.properties.as_ref()
                .and_then(|props| props.get("retryable"))
                .and_then(|v| v.as_bool())
                .unwrap_or(true)
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[tokio::test]
    async fn test_routing_matrix() {
        let matrix = RoutingMatrix::default();
        assert_eq!(matrix.local_small_messages.primary, ChannelType::Ipc);
        assert_eq!(matrix.remote_messages.primary, ChannelType::Tcp);
    }
    
    #[tokio::test]
    async fn test_channel_health() {
        let mut health = ChannelHealth::default();
        health.record_success(Duration::from_millis(5));
        assert_eq!(health.recent_successes, 1);
        assert!(health.error_rate < 0.1);
    }
    
    #[tokio::test]
    async fn test_routing_decision() {
        let router = ChannelRouter::new(RoutingConfig::default());
        let available = vec![ChannelType::Tcp, ChannelType::Ipc];
        
        let characteristics = MessageCharacteristics {
            size: 100,
            priority: MessagePriority::Critical,
            message_type: MessageType::Control,
            target_location: TargetLocation::Local,
            requires_ack: true,
            timeout: Some(Duration::from_millis(10)),
            retryable: true,
        };
        
        let message = crate::message::EncodedMessage::new(vec![1, 2, 3], crate::message::EncodingFormat::Json);
        let decision = router.route_message(&message, "localhost", characteristics, &available).await;
        
        assert!(decision.is_some());
        let decision = decision.unwrap();
        assert_eq!(decision.primary_channel, ChannelType::Ipc); // Should prefer IPC for local critical messages
    }
    
    #[test]
    fn test_message_characteristics_extraction() {
        let message = crate::message::EncodedMessage::new(vec![0; 2048], crate::message::EncodingFormat::Json);
        let characteristics = extract_message_characteristics(&message, None, "127.0.0.1:8080");
        
        assert_eq!(characteristics.size, 2048);
        assert_eq!(characteristics.target_location, TargetLocation::Local);
        assert_eq!(characteristics.message_type, MessageType::Data);
    }
} 