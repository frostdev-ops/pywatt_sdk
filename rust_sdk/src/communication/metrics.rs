//! Performance Monitoring and Metrics for Communication Channels
//!
//! This module provides comprehensive metrics collection, performance monitoring,
//! and health tracking for all communication channels. It supports real-time
//! monitoring, SLA tracking, and performance comparison between channels.

use crate::communication::ChannelType;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant, SystemTime};
use tokio::sync::RwLock as AsyncRwLock;
use tracing::{debug, info, warn};
use uuid::Uuid;

/// Performance metrics for a communication channel
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChannelMetrics {
    /// Channel type
    pub channel_type: ChannelType,
    /// Total number of messages sent
    pub messages_sent: u64,
    /// Total number of messages received
    pub messages_received: u64,
    /// Total bytes sent
    pub bytes_sent: u64,
    /// Total bytes received
    pub bytes_received: u64,
    /// Number of failed operations
    pub failures: u64,
    /// Number of successful operations
    pub successes: u64,
    /// Current error rate (0.0 to 1.0)
    pub error_rate: f64,
    /// Average latency in milliseconds
    pub avg_latency_ms: f64,
    /// 50th percentile latency
    pub p50_latency_ms: f64,
    /// 95th percentile latency
    pub p95_latency_ms: f64,
    /// 99th percentile latency
    pub p99_latency_ms: f64,
    /// Maximum latency observed
    pub max_latency_ms: f64,
    /// Current throughput (messages per second)
    pub throughput_mps: f64,
    /// Current bandwidth utilization (bytes per second)
    pub bandwidth_bps: f64,
    /// Connection uptime
    pub uptime: Duration,
    /// Time when metrics were last updated
    pub last_updated: SystemTime,
    /// Channel availability (0.0 to 1.0)
    pub availability: f64,
    /// Queue depth (pending messages)
    pub queue_depth: u64,
    /// Connection pool statistics
    pub pool_stats: Option<PoolMetrics>,
}

/// Connection pool metrics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PoolMetrics {
    /// Number of active connections
    pub active_connections: usize,
    /// Number of idle connections
    pub idle_connections: usize,
    /// Maximum pool size
    pub max_pool_size: usize,
    /// Total connections created
    pub total_connections_created: u64,
    /// Total connections destroyed
    pub total_connections_destroyed: u64,
    /// Average connection lifetime
    pub avg_connection_lifetime: Duration,
}

impl Default for ChannelMetrics {
    fn default() -> Self {
        Self {
            channel_type: ChannelType::Tcp,
            messages_sent: 0,
            messages_received: 0,
            bytes_sent: 0,
            bytes_received: 0,
            failures: 0,
            successes: 0,
            error_rate: 0.0,
            avg_latency_ms: 0.0,
            p50_latency_ms: 0.0,
            p95_latency_ms: 0.0,
            p99_latency_ms: 0.0,
            max_latency_ms: 0.0,
            throughput_mps: 0.0,
            bandwidth_bps: 0.0,
            uptime: Duration::ZERO,
            last_updated: SystemTime::now(),
            availability: 1.0,
            queue_depth: 0,
            pool_stats: None,
        }
    }
}

/// Latency measurement sample
#[derive(Debug, Clone)]
struct LatencySample {
    latency: Duration,
    timestamp: Instant,
}

/// Throughput measurement sample
#[derive(Debug, Clone)]
struct ThroughputSample {
    count: u64,
    bytes: u64,
    timestamp: Instant,
}

/// SLA (Service Level Agreement) configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SlaConfig {
    /// Target availability (0.0 to 1.0)
    pub target_availability: f64,
    /// Maximum acceptable latency
    pub max_latency: Duration,
    /// Target throughput (messages per second)
    pub target_throughput: f64,
    /// Maximum acceptable error rate (0.0 to 1.0)
    pub max_error_rate: f64,
    /// SLA measurement window
    pub measurement_window: Duration,
}

impl Default for SlaConfig {
    fn default() -> Self {
        Self {
            target_availability: 0.999, // 99.9%
            max_latency: Duration::from_millis(100),
            target_throughput: 1000.0,
            max_error_rate: 0.01, // 1%
            measurement_window: Duration::from_secs(3600), // 1 hour
        }
    }
}

/// SLA compliance status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SlaStatus {
    /// Whether the channel meets SLA requirements
    pub compliant: bool,
    /// Current availability vs target
    pub availability_status: ComplianceStatus,
    /// Current latency vs target
    pub latency_status: ComplianceStatus,
    /// Current throughput vs target
    pub throughput_status: ComplianceStatus,
    /// Current error rate vs target
    pub error_rate_status: ComplianceStatus,
    /// Time window for this status
    pub measurement_window: Duration,
    /// When this status was calculated
    pub calculated_at: SystemTime,
}

/// Compliance status for a specific metric
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceStatus {
    /// Current value
    pub current: f64,
    /// Target value
    pub target: f64,
    /// Whether current meets target
    pub compliant: bool,
    /// Percentage difference from target
    pub difference_percent: f64,
}

/// Performance alert configuration
#[derive(Debug, Clone)]
pub struct AlertConfig {
    /// Latency threshold for alerts
    pub latency_threshold: Duration,
    /// Error rate threshold for alerts
    pub error_rate_threshold: f64,
    /// Throughput drop threshold (percentage)
    pub throughput_drop_threshold: f64,
    /// Availability threshold for alerts
    pub availability_threshold: f64,
    /// Minimum alert interval to prevent spam
    pub min_alert_interval: Duration,
}

impl Default for AlertConfig {
    fn default() -> Self {
        Self {
            latency_threshold: Duration::from_millis(500),
            error_rate_threshold: 0.05, // 5%
            throughput_drop_threshold: 0.5, // 50% drop
            availability_threshold: 0.95, // 95%
            min_alert_interval: Duration::from_secs(300), // 5 minutes
        }
    }
}

/// Performance alert
#[derive(Debug, Clone)]
pub struct PerformanceAlert {
    /// Alert identifier
    pub id: Uuid,
    /// Channel that triggered the alert
    pub channel_type: ChannelType,
    /// Type of alert
    pub alert_type: AlertType,
    /// Alert severity
    pub severity: AlertSeverity,
    /// Alert message
    pub message: String,
    /// Current metric value
    pub current_value: f64,
    /// Threshold that was exceeded
    pub threshold: f64,
    /// When the alert was triggered
    pub triggered_at: SystemTime,
    /// Whether the alert is still active
    pub active: bool,
}

/// Types of performance alerts
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum AlertType {
    HighLatency,
    HighErrorRate,
    LowThroughput,
    LowAvailability,
    ConnectionFailure,
    QueueBacklog,
}

/// Alert severity levels
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub enum AlertSeverity {
    Info,
    Warning,
    Critical,
}

/// Channel performance tracker
pub struct ChannelPerformanceTracker {
    channel_type: ChannelType,
    metrics: Arc<RwLock<ChannelMetrics>>,
    latency_samples: Arc<RwLock<VecDeque<LatencySample>>>,
    throughput_samples: Arc<RwLock<VecDeque<ThroughputSample>>>,
    connection_start_time: Instant,
    sla_config: SlaConfig,
    alert_config: AlertConfig,
    last_alert_times: Arc<RwLock<HashMap<AlertType, Instant>>>,
    sample_window: Duration,
    max_samples: usize,
}

impl ChannelPerformanceTracker {
    /// Create a new performance tracker for a channel
    pub fn new(
        channel_type: ChannelType,
        sla_config: SlaConfig,
        alert_config: AlertConfig,
    ) -> Self {
        Self {
            channel_type,
            metrics: Arc::new(RwLock::new(ChannelMetrics {
                channel_type,
                ..ChannelMetrics::default()
            })),
            latency_samples: Arc::new(RwLock::new(VecDeque::new())),
            throughput_samples: Arc::new(RwLock::new(VecDeque::new())),
            connection_start_time: Instant::now(),
            sla_config,
            alert_config,
            last_alert_times: Arc::new(RwLock::new(HashMap::new())),
            sample_window: Duration::from_secs(300), // 5 minutes
            max_samples: 1000,
        }
    }
    
    /// Record a message sent
    pub fn record_message_sent(&self, bytes: u64, latency: Duration) {
        let mut metrics = self.metrics.write().unwrap();
        metrics.messages_sent += 1;
        metrics.bytes_sent += bytes;
        metrics.successes += 1;
        metrics.last_updated = SystemTime::now();
        metrics.uptime = self.connection_start_time.elapsed();
        drop(metrics);
        
        // Record latency sample
        self.record_latency(latency);
        
        // Update calculated metrics
        self.update_calculated_metrics();
    }
    
    /// Record a message received
    pub fn record_message_received(&self, bytes: u64) {
        let mut metrics = self.metrics.write().unwrap();
        metrics.messages_received += 1;
        metrics.bytes_received += bytes;
        metrics.last_updated = SystemTime::now();
        metrics.uptime = self.connection_start_time.elapsed();
        drop(metrics);
        
        // Update calculated metrics
        self.update_calculated_metrics();
    }
    
    /// Record a failed operation
    pub fn record_failure(&self) {
        let mut metrics = self.metrics.write().unwrap();
        metrics.failures += 1;
        metrics.last_updated = SystemTime::now();
        drop(metrics);
        
        // Update error rate
        self.update_calculated_metrics();
        
        // Check for alerts
        self.check_error_rate_alert();
    }
    
    /// Record connection state change
    pub fn record_connection_state(&self, connected: bool) {
        let mut metrics = self.metrics.write().unwrap();
        if connected {
            metrics.availability = 1.0;
        } else {
            metrics.availability = 0.0;
            metrics.failures += 1;
        }
        metrics.last_updated = SystemTime::now();
        drop(metrics);
        
        if !connected {
            self.trigger_alert(
                AlertType::ConnectionFailure,
                AlertSeverity::Critical,
                "Channel connection lost".to_string(),
                0.0,
                1.0,
            );
        }
    }
    
    /// Update queue depth
    pub fn update_queue_depth(&self, depth: u64) {
        let mut metrics = self.metrics.write().unwrap();
        metrics.queue_depth = depth;
        metrics.last_updated = SystemTime::now();
        drop(metrics);
        
        // Check for queue backlog alert
        if depth > 1000 { // Configurable threshold
            self.trigger_alert(
                AlertType::QueueBacklog,
                AlertSeverity::Warning,
                format!("High queue depth: {} messages", depth),
                depth as f64,
                1000.0,
            );
        }
    }
    
    /// Update pool statistics
    pub fn update_pool_stats(&self, pool_stats: PoolMetrics) {
        let mut metrics = self.metrics.write().unwrap();
        metrics.pool_stats = Some(pool_stats);
        metrics.last_updated = SystemTime::now();
    }
    
    /// Get current metrics snapshot
    pub fn get_metrics(&self) -> ChannelMetrics {
        self.metrics.read().unwrap().clone()
    }
    
    /// Get SLA compliance status
    pub fn get_sla_status(&self) -> SlaStatus {
        let metrics = self.metrics.read().unwrap();
        
        let availability_status = ComplianceStatus {
            current: metrics.availability,
            target: self.sla_config.target_availability,
            compliant: metrics.availability >= self.sla_config.target_availability,
            difference_percent: ((metrics.availability - self.sla_config.target_availability) 
                                / self.sla_config.target_availability * 100.0),
        };
        
        let latency_status = ComplianceStatus {
            current: metrics.p95_latency_ms,
            target: self.sla_config.max_latency.as_millis() as f64,
            compliant: Duration::from_millis(metrics.p95_latency_ms as u64) <= self.sla_config.max_latency,
            difference_percent: ((metrics.p95_latency_ms - self.sla_config.max_latency.as_millis() as f64) 
                                / self.sla_config.max_latency.as_millis() as f64 * 100.0),
        };
        
        let throughput_status = ComplianceStatus {
            current: metrics.throughput_mps,
            target: self.sla_config.target_throughput,
            compliant: metrics.throughput_mps >= self.sla_config.target_throughput,
            difference_percent: ((metrics.throughput_mps - self.sla_config.target_throughput) 
                                / self.sla_config.target_throughput * 100.0),
        };
        
        let error_rate_status = ComplianceStatus {
            current: metrics.error_rate,
            target: self.sla_config.max_error_rate,
            compliant: metrics.error_rate <= self.sla_config.max_error_rate,
            difference_percent: ((metrics.error_rate - self.sla_config.max_error_rate) 
                                / self.sla_config.max_error_rate * 100.0),
        };
        
        let compliant = availability_status.compliant && 
                       latency_status.compliant && 
                       throughput_status.compliant && 
                       error_rate_status.compliant;
        
        SlaStatus {
            compliant,
            availability_status,
            latency_status,
            throughput_status,
            error_rate_status,
            measurement_window: self.sla_config.measurement_window,
            calculated_at: SystemTime::now(),
        }
    }
    
    /// Reset metrics (useful for testing or periodic resets)
    pub fn reset_metrics(&self) {
        let mut metrics = self.metrics.write().unwrap();
        *metrics = ChannelMetrics {
            channel_type: self.channel_type,
            ..ChannelMetrics::default()
        };
        drop(metrics);
        
        let mut latency_samples = self.latency_samples.write().unwrap();
        latency_samples.clear();
        drop(latency_samples);
        
        let mut throughput_samples = self.throughput_samples.write().unwrap();
        throughput_samples.clear();
    }
    
    // Private helper methods
    
    fn record_latency(&self, latency: Duration) {
        let mut samples = self.latency_samples.write().unwrap();
        let now = Instant::now();
        
        samples.push_back(LatencySample {
            latency,
            timestamp: now,
        });
        
        // Remove old samples outside the window
        while let Some(front) = samples.front() {
            if now.duration_since(front.timestamp) > self.sample_window {
                samples.pop_front();
            } else {
                break;
            }
        }
        
        // Limit total samples
        while samples.len() > self.max_samples {
            samples.pop_front();
        }
        
        // Check for latency alert
        if latency > self.alert_config.latency_threshold {
            self.trigger_alert(
                AlertType::HighLatency,
                AlertSeverity::Warning,
                format!("High latency detected: {}ms", latency.as_millis()),
                latency.as_millis() as f64,
                self.alert_config.latency_threshold.as_millis() as f64,
            );
        }
    }
    
    fn update_calculated_metrics(&self) {
        let mut metrics = self.metrics.write().unwrap();
        
        // Update error rate
        let total_ops = metrics.successes + metrics.failures;
        if total_ops > 0 {
            metrics.error_rate = metrics.failures as f64 / total_ops as f64;
        }
        
        // Update latency percentiles
        let latency_samples = self.latency_samples.read().unwrap();
        if !latency_samples.is_empty() {
            let mut latencies: Vec<Duration> = latency_samples.iter()
                .map(|sample| sample.latency)
                .collect();
            latencies.sort();
            
            let len = latencies.len();
            metrics.avg_latency_ms = latencies.iter()
                .map(|d| d.as_millis() as f64)
                .sum::<f64>() / len as f64;
            
            metrics.p50_latency_ms = latencies[len / 2].as_millis() as f64;
            metrics.p95_latency_ms = latencies[(len as f64 * 0.95) as usize].as_millis() as f64;
            metrics.p99_latency_ms = latencies[(len as f64 * 0.99) as usize].as_millis() as f64;
            metrics.max_latency_ms = latencies[len - 1].as_millis() as f64;
        }
        drop(latency_samples);
        
        // Update throughput
        let throughput_samples = self.throughput_samples.read().unwrap();
        if !throughput_samples.is_empty() {
            let now = Instant::now();
            let recent_samples: Vec<&ThroughputSample> = throughput_samples.iter()
                .filter(|sample| now.duration_since(sample.timestamp) <= Duration::from_secs(60))
                .collect();
                
            if !recent_samples.is_empty() {
                let total_messages: u64 = recent_samples.iter().map(|s| s.count).sum();
                let total_bytes: u64 = recent_samples.iter().map(|s| s.bytes).sum();
                let time_span = Duration::from_secs(60); // 1 minute window
                
                metrics.throughput_mps = total_messages as f64 / time_span.as_secs_f64();
                metrics.bandwidth_bps = total_bytes as f64 / time_span.as_secs_f64();
            }
        }
        drop(throughput_samples);
        
        // Record throughput sample
        let mut throughput_samples = self.throughput_samples.write().unwrap();
        throughput_samples.push_back(ThroughputSample {
            count: 1,
            bytes: 0, // This should be passed in somehow
            timestamp: Instant::now(),
        });
        
        // Clean old throughput samples
        let now = Instant::now();
        while let Some(front) = throughput_samples.front() {
            if now.duration_since(front.timestamp) > self.sample_window {
                throughput_samples.pop_front();
            } else {
                break;
            }
        }
    }
    
    fn check_error_rate_alert(&self) {
        let metrics = self.metrics.read().unwrap();
        
        if metrics.error_rate > self.alert_config.error_rate_threshold {
            self.trigger_alert(
                AlertType::HighErrorRate,
                AlertSeverity::Warning,
                format!("High error rate: {:.2}%", metrics.error_rate * 100.0),
                metrics.error_rate,
                self.alert_config.error_rate_threshold,
            );
        }
    }
    
    fn trigger_alert(
        &self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: String,
        current_value: f64,
        threshold: f64,
    ) {
        // Check if enough time has passed since last alert of this type
        let mut last_alert_times = self.last_alert_times.write().unwrap();
        let now = Instant::now();
        
        if let Some(last_time) = last_alert_times.get(&alert_type) {
            if now.duration_since(*last_time) < self.alert_config.min_alert_interval {
                return; // Skip alert to prevent spam
            }
        }
        
        last_alert_times.insert(alert_type.clone(), now);
        drop(last_alert_times);
        
        let alert = PerformanceAlert {
            id: Uuid::new_v4(),
            channel_type: self.channel_type,
            alert_type: alert_type.clone(),
            severity: severity.clone(),
            message: message.clone(),
            current_value,
            threshold,
            triggered_at: SystemTime::now(),
            active: true,
        };
        
        // Log the alert
        match severity {
            AlertSeverity::Info => info!("Performance alert: {}", message),
            AlertSeverity::Warning => warn!("Performance alert: {}", message),
            AlertSeverity::Critical => tracing::error!("Performance alert: {}", message),
        }
        
        // In a real implementation, you might want to:
        // - Send alerts to external monitoring systems
        // - Store alerts in a database
        // - Send notifications to administrators
        debug!("Alert triggered: {:?}", alert);
    }
}

/// Global performance monitoring system
pub struct PerformanceMonitoringSystem {
    trackers: Arc<AsyncRwLock<HashMap<ChannelType, Arc<ChannelPerformanceTracker>>>>,
    sla_config: SlaConfig,
    alert_config: AlertConfig,
    monitoring_enabled: bool,
}

impl PerformanceMonitoringSystem {
    /// Create a new performance monitoring system
    pub fn new(sla_config: SlaConfig, alert_config: AlertConfig) -> Self {
        Self {
            trackers: Arc::new(AsyncRwLock::new(HashMap::new())),
            sla_config,
            alert_config,
            monitoring_enabled: true,
        }
    }
    
    /// Enable or disable monitoring
    pub fn set_monitoring_enabled(&mut self, enabled: bool) {
        self.monitoring_enabled = enabled;
    }
    
    /// Get or create a tracker for a channel
    pub async fn get_tracker(&self, channel_type: ChannelType) -> Arc<ChannelPerformanceTracker> {
        let mut trackers = self.trackers.write().await;
        
        trackers.entry(channel_type)
            .or_insert_with(|| {
                Arc::new(ChannelPerformanceTracker::new(
                    channel_type,
                    self.sla_config.clone(),
                    self.alert_config.clone(),
                ))
            })
            .clone()
    }
    
    /// Get all channel metrics
    pub async fn get_all_metrics(&self) -> HashMap<ChannelType, ChannelMetrics> {
        let trackers = self.trackers.read().await;
        
        trackers.iter()
            .map(|(&channel_type, tracker)| (channel_type, tracker.get_metrics()))
            .collect()
    }
    
    /// Get SLA status for all channels
    pub async fn get_all_sla_status(&self) -> HashMap<ChannelType, SlaStatus> {
        let trackers = self.trackers.read().await;
        
        trackers.iter()
            .map(|(&channel_type, tracker)| (channel_type, tracker.get_sla_status()))
            .collect()
    }
    
    /// Get comparative performance report
    pub async fn get_performance_comparison(&self) -> PerformanceComparisonReport {
        let all_metrics = self.get_all_metrics().await;
        
        let mut best_latency: Option<(ChannelType, f64)> = None;
        let mut best_throughput: Option<(ChannelType, f64)> = None;
        let mut best_availability: Option<(ChannelType, f64)> = None;
        let mut lowest_error_rate: Option<(ChannelType, f64)> = None;
        
        for (channel_type, metrics) in &all_metrics {
            // Best latency (lowest)
            if best_latency.is_none() || metrics.p95_latency_ms < best_latency.unwrap().1 {
                best_latency = Some((*channel_type, metrics.p95_latency_ms));
            }
            
            // Best throughput (highest)
            if best_throughput.is_none() || metrics.throughput_mps > best_throughput.unwrap().1 {
                best_throughput = Some((*channel_type, metrics.throughput_mps));
            }
            
            // Best availability (highest)
            if best_availability.is_none() || metrics.availability > best_availability.unwrap().1 {
                best_availability = Some((*channel_type, metrics.availability));
            }
            
            // Lowest error rate
            if lowest_error_rate.is_none() || metrics.error_rate < lowest_error_rate.unwrap().1 {
                lowest_error_rate = Some((*channel_type, metrics.error_rate));
            }
        }
        
        PerformanceComparisonReport {
            metrics: all_metrics,
            best_latency,
            best_throughput,
            best_availability,
            lowest_error_rate,
            generated_at: SystemTime::now(),
        }
    }
    
    /// Reset all metrics
    pub async fn reset_all_metrics(&self) {
        let trackers = self.trackers.read().await;
        
        for tracker in trackers.values() {
            tracker.reset_metrics();
        }
    }
}

/// Performance comparison report
#[derive(Debug, Clone)]
pub struct PerformanceComparisonReport {
    /// All channel metrics
    pub metrics: HashMap<ChannelType, ChannelMetrics>,
    /// Channel with best latency (lowest)
    pub best_latency: Option<(ChannelType, f64)>,
    /// Channel with best throughput (highest)
    pub best_throughput: Option<(ChannelType, f64)>,
    /// Channel with best availability (highest)
    pub best_availability: Option<(ChannelType, f64)>,
    /// Channel with lowest error rate
    pub lowest_error_rate: Option<(ChannelType, f64)>,
    /// When this report was generated
    pub generated_at: SystemTime,
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    
    
    #[test]
    fn test_channel_metrics_creation() {
        let sla_config = SlaConfig::default();
        let alert_config = AlertConfig::default();
        let tracker = ChannelPerformanceTracker::new(
            ChannelType::Tcp,
            sla_config,
            alert_config,
        );
        
        let metrics = tracker.get_metrics();
        assert_eq!(metrics.channel_type, ChannelType::Tcp);
        assert_eq!(metrics.messages_sent, 0);
        assert_eq!(metrics.error_rate, 0.0);
    }
    
    #[test]
    fn test_message_recording() {
        let sla_config = SlaConfig::default();
        let alert_config = AlertConfig::default();
        let tracker = ChannelPerformanceTracker::new(
            ChannelType::Tcp,
            sla_config,
            alert_config,
        );
        
        tracker.record_message_sent(1024, Duration::from_millis(50));
        tracker.record_message_received(512);
        
        let metrics = tracker.get_metrics();
        assert_eq!(metrics.messages_sent, 1);
        assert_eq!(metrics.messages_received, 1);
        assert_eq!(metrics.bytes_sent, 1024);
        assert_eq!(metrics.bytes_received, 512);
        assert!(metrics.avg_latency_ms > 0.0);
    }
    
    #[test]
    fn test_error_rate_calculation() {
        let sla_config = SlaConfig::default();
        let alert_config = AlertConfig::default();
        let tracker = ChannelPerformanceTracker::new(
            ChannelType::Tcp,
            sla_config,
            alert_config,
        );
        
        // Record some successes and failures
        tracker.record_message_sent(100, Duration::from_millis(10));
        tracker.record_message_sent(100, Duration::from_millis(10));
        tracker.record_failure();
        
        let metrics = tracker.get_metrics();
        assert_eq!(metrics.successes, 2);
        assert_eq!(metrics.failures, 1);
        assert!((metrics.error_rate - 0.333).abs() < 0.01); // ~33.3%
    }
    
    #[test]
    fn test_sla_status() {
        let sla_config = SlaConfig {
            target_availability: 0.99,
            max_latency: Duration::from_millis(100),
            target_throughput: 10.0,
            max_error_rate: 0.05,
            measurement_window: Duration::from_secs(60),
        };
        let alert_config = AlertConfig::default();
        let tracker = ChannelPerformanceTracker::new(
            ChannelType::Tcp,
            sla_config,
            alert_config,
        );
        
        // Record some good performance
        for _ in 0..10 {
            tracker.record_message_sent(100, Duration::from_millis(20));
        }
        
        let sla_status = tracker.get_sla_status();
        assert!(sla_status.availability_status.compliant);
        assert!(sla_status.latency_status.compliant);
        assert!(sla_status.error_rate_status.compliant);
    }
    
    #[tokio::test]
    async fn test_monitoring_system() {
        let sla_config = SlaConfig::default();
        let alert_config = AlertConfig::default();
        let monitoring = PerformanceMonitoringSystem::new(sla_config, alert_config);
        
        let tcp_tracker = monitoring.get_tracker(ChannelType::Tcp).await;
        let ipc_tracker = monitoring.get_tracker(ChannelType::Ipc).await;
        
        tcp_tracker.record_message_sent(1000, Duration::from_millis(30));
        ipc_tracker.record_message_sent(500, Duration::from_millis(5));
        
        let all_metrics = monitoring.get_all_metrics().await;
        assert_eq!(all_metrics.len(), 2);
        assert!(all_metrics.contains_key(&ChannelType::Tcp));
        assert!(all_metrics.contains_key(&ChannelType::Ipc));
        
        let comparison = monitoring.get_performance_comparison().await;
        assert!(comparison.best_latency.is_some());
        assert_eq!(comparison.best_latency.unwrap().0, ChannelType::Ipc); // IPC should have better latency
    }
} 