//! Advanced Failover Mechanisms and Performance Optimizations
//!
//! This module provides robust failover capabilities, circuit breaker patterns,
//! performance optimizations including connection pooling, message batching,
//! and intelligent retry mechanisms.

use crate::communication::{ChannelType, MessageChannel};
use crate::message::{EncodedMessage, MessageError};
use std::collections::HashMap;
use std::sync::{Arc, Mutex, RwLock};
use std::time::{Duration, Instant};
use tokio::sync::{mpsc, Semaphore};
#[allow(unused_imports)] // Used in test code
use tokio::time::{sleep, timeout};
use tracing::{debug, warn, error, info};
use uuid::Uuid;

#[cfg(feature = "advanced_failover")]
use flate2::{read::GzDecoder, write::GzEncoder, Compression};

#[cfg(feature = "advanced_failover")]
use std::io::{Read, Write};

/// Circuit breaker states
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CircuitBreakerState {
    /// Circuit is closed, requests flow normally
    Closed,
    /// Circuit is open, requests are immediately rejected
    Open,
    /// Circuit is half-open, allowing limited requests to test recovery
    HalfOpen,
}

/// Circuit breaker configuration
#[derive(Debug, Clone)]
pub struct CircuitBreakerConfig {
    /// Failure threshold to open the circuit
    pub failure_threshold: u32,
    /// Success threshold to close circuit from half-open
    pub success_threshold: u32,
    /// Timeout before transitioning from open to half-open
    pub timeout: Duration,
    /// Window size for failure counting
    pub window_size: Duration,
    /// Minimum number of requests before evaluating circuit state
    pub minimum_requests: u32,
}

impl Default for CircuitBreakerConfig {
    fn default() -> Self {
        Self {
            failure_threshold: 5,
            success_threshold: 3,
            timeout: Duration::from_secs(60),
            window_size: Duration::from_secs(60),
            minimum_requests: 10,
        }
    }
}

/// Circuit breaker for channel failure detection and protection
#[derive(Clone)]
pub struct CircuitBreaker {
    state: Arc<RwLock<CircuitBreakerState>>,
    config: CircuitBreakerConfig,
    failure_count: Arc<RwLock<u32>>,
    success_count: Arc<RwLock<u32>>,
    last_failure_time: Arc<RwLock<Option<Instant>>>,
    request_count: Arc<RwLock<u32>>,
    window_start: Arc<RwLock<Instant>>,
}

impl CircuitBreaker {
    /// Create a new circuit breaker
    pub fn new(config: CircuitBreakerConfig) -> Self {
        Self {
            state: Arc::new(RwLock::new(CircuitBreakerState::Closed)),
            config,
            failure_count: Arc::new(RwLock::new(0)),
            success_count: Arc::new(RwLock::new(0)),
            last_failure_time: Arc::new(RwLock::new(None)),
            request_count: Arc::new(RwLock::new(0)),
            window_start: Arc::new(RwLock::new(Instant::now())),
        }
    }
    
    /// Check if the circuit allows a request
    pub async fn can_execute(&self) -> bool {
        let state = *self.state.read().unwrap();
        
        match state {
            CircuitBreakerState::Closed => true,
            CircuitBreakerState::Open => {
                // Check if enough time has passed to try half-open
                if let Some(last_failure) = *self.last_failure_time.read().unwrap() {
                    if last_failure.elapsed() > self.config.timeout {
                        self.transition_to_half_open().await;
                        true
                    } else {
                        false
                    }
                } else {
                    true
                }
            }
            CircuitBreakerState::HalfOpen => true, // Allow limited requests in half-open
        }
    }
    
    /// Record a successful execution
    pub async fn record_success(&self) {
        {
            let mut success_count = self.success_count.write().unwrap();
            *success_count += 1;
        }
        
        self.increment_request_count().await;
        
        let state = *self.state.read().unwrap();
        if state == CircuitBreakerState::HalfOpen {
            let success_count = *self.success_count.read().unwrap();
            if success_count >= self.config.success_threshold {
                self.transition_to_closed().await;
            }
        }
    }
    
    /// Record a failed execution
    pub async fn record_failure(&self) {
        {
            let mut failure_count = self.failure_count.write().unwrap();
            *failure_count += 1;
            
            let mut last_failure_time = self.last_failure_time.write().unwrap();
            *last_failure_time = Some(Instant::now());
        }
        
        self.increment_request_count().await;
        self.evaluate_state().await;
    }
    
    /// Get current circuit breaker state
    pub fn get_state(&self) -> CircuitBreakerState {
        *self.state.read().unwrap()
    }
    
    /// Get failure statistics
    pub fn get_stats(&self) -> CircuitBreakerStats {
        CircuitBreakerStats {
            state: self.get_state(),
            failure_count: *self.failure_count.read().unwrap(),
            success_count: *self.success_count.read().unwrap(),
            request_count: *self.request_count.read().unwrap(),
            last_failure_time: *self.last_failure_time.read().unwrap(),
        }
    }
    
    async fn increment_request_count(&self) {
        let mut request_count = self.request_count.write().unwrap();
        *request_count += 1;
        
        // Reset window if needed
        let window_start = *self.window_start.read().unwrap();
        if window_start.elapsed() > self.config.window_size {
            *request_count = 1;
            drop(request_count);
            
            let mut new_window_start = self.window_start.write().unwrap();
            *new_window_start = Instant::now();
            
            let mut failure_count = self.failure_count.write().unwrap();
            *failure_count = 0;
            
            let mut success_count = self.success_count.write().unwrap();
            *success_count = 0;
        }
    }
    
    async fn evaluate_state(&self) {
        let request_count = *self.request_count.read().unwrap();
        let failure_count = *self.failure_count.read().unwrap();
        
        if request_count >= self.config.minimum_requests &&
           failure_count >= self.config.failure_threshold {
            self.transition_to_open().await;
        }
    }
    
    async fn transition_to_open(&self) {
        let mut state = self.state.write().unwrap();
        if *state != CircuitBreakerState::Open {
            *state = CircuitBreakerState::Open;
            warn!("Circuit breaker opened due to failures");
        }
    }
    
    async fn transition_to_half_open(&self) {
        let mut state = self.state.write().unwrap();
        *state = CircuitBreakerState::HalfOpen;
        
        // Reset success count for half-open evaluation
        let mut success_count = self.success_count.write().unwrap();
        *success_count = 0;
        
        info!("Circuit breaker transitioned to half-open");
    }
    
    async fn transition_to_closed(&self) {
        let mut state = self.state.write().unwrap();
        *state = CircuitBreakerState::Closed;
        
        // Reset counters
        let mut failure_count = self.failure_count.write().unwrap();
        *failure_count = 0;
        
        let mut success_count = self.success_count.write().unwrap();
        *success_count = 0;
        
        info!("Circuit breaker closed - channel recovered");
    }
}

/// Circuit breaker statistics
#[derive(Debug, Clone)]
pub struct CircuitBreakerStats {
    pub state: CircuitBreakerState,
    pub failure_count: u32,
    pub success_count: u32,
    pub request_count: u32,
    pub last_failure_time: Option<Instant>,
}

/// Retry policy configuration
#[derive(Debug, Clone)]
pub struct RetryConfig {
    /// Maximum number of retry attempts
    pub max_attempts: u32,
    /// Base delay between retries
    pub base_delay: Duration,
    /// Maximum delay between retries
    pub max_delay: Duration,
    /// Exponential backoff multiplier
    pub backoff_multiplier: f64,
    /// Jitter factor to prevent thundering herd
    pub jitter_factor: f64,
    /// Whether to retry on all errors or only specific ones
    pub retry_on_all_errors: bool,
}

impl Default for RetryConfig {
    fn default() -> Self {
        Self {
            max_attempts: 3,
            base_delay: Duration::from_millis(100),
            max_delay: Duration::from_secs(30),
            backoff_multiplier: 2.0,
            jitter_factor: 0.1,
            retry_on_all_errors: false,
        }
    }
}

/// Retry mechanism with exponential backoff and jitter
pub struct RetryMechanism {
    config: RetryConfig,
}

impl RetryMechanism {
    /// Create a new retry mechanism
    pub fn new(config: RetryConfig) -> Self {
        Self { config }
    }
    
    /// Execute a function with retry logic
    pub async fn execute<F, Fut, T, E>(&self, mut operation: F) -> Result<T, E>
    where
        F: FnMut() -> Fut,
        Fut: std::future::Future<Output = Result<T, E>>,
        E: std::fmt::Debug,
    {
        let mut attempt = 0;
        let mut delay = self.config.base_delay;
        
        loop {
            attempt += 1;
            
            match operation().await {
                Ok(result) => {
                    if attempt > 1 {
                        debug!("Operation succeeded after {} attempts", attempt);
                    }
                    return Ok(result);
                }
                Err(error) => {
                    if attempt >= self.config.max_attempts {
                        error!("Operation failed after {} attempts: {:?}", attempt, error);
                        return Err(error);
                    }
                    
                    if !self.config.retry_on_all_errors {
                        // Add logic here to determine if error is retryable
                        // For now, retry all errors
                    }
                    
                    debug!("Operation failed on attempt {}, retrying in {:?}: {:?}", 
                           attempt, delay, error);
                    
                    // Add jitter to prevent thundering herd
                    #[cfg(feature = "advanced_failover")]
                    let jitter = (fastrand::f64() - 0.5) * self.config.jitter_factor;
                    
                    #[cfg(not(feature = "advanced_failover"))]
                    let jitter = {
                        use std::collections::hash_map::DefaultHasher;
                        use std::hash::{Hash, Hasher};
                        let mut hasher = DefaultHasher::new();
                        std::time::SystemTime::now().hash(&mut hasher);
                        let hash = hasher.finish();
                        ((hash % 1000) as f64 / 1000.0 - 0.5) * self.config.jitter_factor
                    };
                    
                    let jittered_delay = delay.mul_f64(1.0 + jitter);
                    
                    sleep(jittered_delay).await;
                    
                    // Exponential backoff
                    delay = std::cmp::min(
                        delay.mul_f64(self.config.backoff_multiplier),
                        self.config.max_delay,
                    );
                }
            }
        }
    }
}

/// Message batching configuration
#[derive(Debug, Clone)]
pub struct BatchConfig {
    /// Maximum number of messages per batch
    pub max_batch_size: usize,
    /// Maximum time to wait before sending a partial batch
    pub max_batch_delay: Duration,
    /// Maximum total size of a batch in bytes
    pub max_batch_bytes: usize,
    /// Whether to preserve message ordering within batches
    pub preserve_order: bool,
}

impl Default for BatchConfig {
    fn default() -> Self {
        Self {
            max_batch_size: 100,
            max_batch_delay: Duration::from_millis(10),
            max_batch_bytes: 1024 * 1024, // 1MB
            preserve_order: true,
        }
    }
}

/// Message batch for efficient transmission
#[derive(Debug, Clone)]
pub struct MessageBatch {
    /// Messages in the batch
    pub messages: Vec<EncodedMessage>,
    /// Total size of the batch in bytes
    pub total_size: usize,
    /// When the batch was created
    pub created_at: Instant,
    /// Batch identifier
    pub batch_id: Uuid,
}

impl Default for MessageBatch {
    fn default() -> Self {
        Self::new()
    }
}

impl MessageBatch {
    /// Create a new empty batch
    pub fn new() -> Self {
        Self {
            messages: Vec::new(),
            total_size: 0,
            created_at: Instant::now(),
            batch_id: Uuid::new_v4(),
        }
    }
    
    /// Add a message to the batch
    pub fn add_message(&mut self, message: EncodedMessage) -> bool {
        let message_size = message.data().len();
        if self.can_add(message_size) {
            self.total_size += message_size;
            self.messages.push(message);
            true
        } else {
            false
        }
    }
    
    /// Check if the batch is ready to send based on configuration
    pub fn is_ready(&self, config: &BatchConfig) -> bool {
        self.messages.len() >= config.max_batch_size ||
        self.total_size >= config.max_batch_bytes ||
        self.created_at.elapsed() >= config.max_batch_delay
    }
    
    /// Check if the batch is empty
    pub fn is_empty(&self) -> bool {
        self.messages.is_empty()
    }
    
    /// Get the number of messages in the batch
    pub fn len(&self) -> usize {
        self.messages.len()
    }
    
    pub fn can_add(&self, message_size: usize) -> bool {
        // Check for overflow potential instead of comparing with usize::MAX
        self.total_size.checked_add(message_size).is_some()
    }
}

/// Message batcher for efficient bulk transmission
pub struct MessageBatcher {
    config: BatchConfig,
    pending_batch: Arc<Mutex<MessageBatch>>,
    sender: mpsc::UnboundedSender<MessageBatch>,
    receiver: Arc<Mutex<mpsc::UnboundedReceiver<MessageBatch>>>,
}

impl MessageBatcher {
    /// Create a new message batcher
    pub fn new(config: BatchConfig) -> Self {
        let (sender, receiver) = mpsc::unbounded_channel();
        
        Self {
            config,
            pending_batch: Arc::new(Mutex::new(MessageBatch::new())),
            sender,
            receiver: Arc::new(Mutex::new(receiver)),
        }
    }
    
    /// Add a message to the batcher
    pub async fn add_message(&self, message: EncodedMessage) -> Result<(), MessageError> {
        let mut batch = self.pending_batch.lock().unwrap();
        
        if !batch.add_message(message.clone()) {
            // Current batch is full, send it and start a new one
            if !batch.is_empty() {
                let ready_batch = std::mem::take(&mut *batch);
                self.sender.send(ready_batch)
                    .map_err(|_| MessageError::InvalidFormat("Batch channel closed".to_string()))?;
            }
            
            // Try adding to new batch
            if !batch.add_message(message) {
                return Err(MessageError::InvalidFormat("Message too large for batch".to_string()));
            }
        }
        
        // Check if batch is ready to send
        if batch.is_ready(&self.config) {
            let ready_batch = std::mem::take(&mut *batch);
            self.sender.send(ready_batch)
                .map_err(|_| MessageError::InvalidFormat("Batch channel closed".to_string()))?;
        }
        
        Ok(())
    }
    
    /// Force flush any pending batch
    pub async fn flush(&self) -> Result<(), MessageError> {
        let mut batch = self.pending_batch.lock().unwrap();
        
        if !batch.is_empty() {
            let ready_batch = std::mem::take(&mut *batch);
            self.sender.send(ready_batch)
                .map_err(|_| MessageError::InvalidFormat("Batch channel closed".to_string()))?;
        }
        
        Ok(())
    }
    
    /// Receive the next ready batch
    pub async fn receive_batch(&self) -> Option<MessageBatch> {
        let mut receiver = self.receiver.lock().unwrap();
        receiver.recv().await
    }
}

/// Connection pool for managing multiple connections to the same endpoint
pub struct ConnectionPool<T: MessageChannel + Clone> {
    connections: Arc<RwLock<Vec<Arc<T>>>>,
    semaphore: Arc<Semaphore>,
    max_connections: usize,
    connection_factory: Box<dyn Fn() -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<T, MessageError>> + Send>> + Send + Sync>,
}

impl<T: MessageChannel + Clone + Send + Sync + 'static> ConnectionPool<T> {
    /// Create a new connection pool
    pub fn new<F, Fut>(
        max_connections: usize, 
        connection_factory: F
    ) -> Self 
    where
        F: Fn() -> Fut + Send + Sync + 'static,
        Fut: std::future::Future<Output = Result<T, MessageError>> + Send + 'static,
    {
        Self {
            connections: Arc::new(RwLock::new(Vec::new())),
            semaphore: Arc::new(Semaphore::new(max_connections)),
            max_connections,
            connection_factory: Box::new(move || Box::pin(connection_factory())),
        }
    }
    
    /// Get a connection from the pool
    pub async fn get_connection(&self) -> Result<PooledConnection<T>, MessageError> {
        // Acquire semaphore permit
        let permit = self.semaphore.clone().acquire_owned().await
            .map_err(|_| MessageError::InvalidFormat("Pool semaphore closed".to_string()))?;
        
        // Try to get an existing connection
        {
            let mut connections = self.connections.write().unwrap();
            if let Some(connection) = connections.pop() {
                return Ok(PooledConnection::new(connection, self.connections.clone(), permit));
            }
        }
        
        // Create a new connection
        let connection = (self.connection_factory)().await?;
        Ok(PooledConnection::new(
            Arc::new(connection), 
            self.connections.clone(), 
            permit
        ))
    }
    
    /// Get pool statistics
    pub fn get_stats(&self) -> PoolStats {
        let connections = self.connections.read().unwrap();
        PoolStats {
            available_connections: connections.len(),
            max_connections: self.max_connections,
            active_connections: self.max_connections - self.semaphore.available_permits(),
        }
    }
}

/// A pooled connection that returns to the pool when dropped
pub struct PooledConnection<T: MessageChannel> {
    connection: Option<Arc<T>>,
    pool: Arc<RwLock<Vec<Arc<T>>>>,
    _permit: tokio::sync::OwnedSemaphorePermit,
}

impl<T: MessageChannel> PooledConnection<T> {
    fn new(
        connection: Arc<T>, 
        pool: Arc<RwLock<Vec<Arc<T>>>>,
        permit: tokio::sync::OwnedSemaphorePermit,
    ) -> Self {
        Self {
            connection: Some(connection),
            pool,
            _permit: permit,
        }
    }
    
    /// Get a reference to the underlying connection
    pub fn connection(&self) -> &T {
        self.connection.as_ref().unwrap()
    }
}

impl<T: MessageChannel> Drop for PooledConnection<T> {
    fn drop(&mut self) {
        if let Some(connection) = self.connection.take() {
            let mut pool = self.pool.write().unwrap();
            pool.push(connection);
        }
    }
}

/// Connection pool statistics
#[derive(Debug, Clone)]
pub struct PoolStats {
    pub available_connections: usize,
    pub max_connections: usize,
    pub active_connections: usize,
}

/// Performance optimization configuration
#[derive(Debug, Clone)]
pub struct PerformanceConfig {
    /// Enable message compression for large messages
    pub enable_compression: bool,
    /// Compression threshold in bytes
    pub compression_threshold: usize,
    /// Enable zero-copy optimizations where possible
    pub enable_zero_copy: bool,
    /// Buffer size for I/O operations
    pub io_buffer_size: usize,
    /// Enable TCP_NODELAY for low latency
    pub tcp_nodelay: bool,
    /// TCP send buffer size
    pub tcp_send_buffer: Option<usize>,
    /// TCP receive buffer size
    pub tcp_recv_buffer: Option<usize>,
}

impl Default for PerformanceConfig {
    fn default() -> Self {
        Self {
            enable_compression: true,
            compression_threshold: 1024, // 1KB
            enable_zero_copy: true,
            io_buffer_size: 64 * 1024, // 64KB
            tcp_nodelay: true,
            tcp_send_buffer: Some(256 * 1024), // 256KB
            tcp_recv_buffer: Some(256 * 1024), // 256KB
        }
    }
}

/// Message compression utilities
pub struct MessageCompressor {
    config: PerformanceConfig,
}

impl MessageCompressor {
    /// Create a new message compressor
    pub fn new(config: PerformanceConfig) -> Self {
        Self { config }
    }
    
    /// Compress a message if it meets the threshold
    pub fn compress_message(&self, _message: &mut EncodedMessage) -> Result<bool, MessageError> {
        #[cfg(feature = "advanced_failover")]
        {
            if !self.config.enable_compression {
                return Ok(false);
            }
            
            if message.data().len() < self.config.compression_threshold {
                return Ok(false);
            }
            
            // Simple compression using flate2 (gzip)
            let mut encoder = GzEncoder::new(Vec::new(), Compression::fast());
            encoder.write_all(message.data())
                .map_err(|e| MessageError::InvalidFormat(format!("Compression failed: {}", e)))?;
            
            let compressed_data = encoder.finish()
                .map_err(|e| MessageError::InvalidFormat(format!("Compression failed: {}", e)))?;
            
            // Only use compressed version if it's actually smaller
            if compressed_data.len() < message.data().len() {
                *message = EncodedMessage::new(compressed_data, message.format());
                Ok(true)
            } else {
                Ok(false)
            }
        }
        
        #[cfg(not(feature = "advanced_failover"))]
        {
            // Compression not available without feature
            Ok(false)
        }
    }
    
    /// Decompress a message
    pub fn decompress_message(&self, _message: &mut EncodedMessage) -> Result<(), MessageError> {
        #[cfg(feature = "advanced_failover")]
        {
            let mut decoder = GzDecoder::new(message.data());
            let mut decompressed_data = Vec::new();
            
            decoder.read_to_end(&mut decompressed_data)
                .map_err(|e| MessageError::InvalidFormat(format!("Decompression failed: {}", e)))?;
            
            *message = EncodedMessage::new(decompressed_data, message.format());
            Ok(())
        }
        
        #[cfg(not(feature = "advanced_failover"))]
        {
            Err(MessageError::InvalidFormat("Decompression not available without advanced_failover feature".to_string()))
        }
    }
}

/// Comprehensive failover manager that coordinates all failover mechanisms
pub struct FailoverManager {
    circuit_breakers: Arc<RwLock<HashMap<ChannelType, CircuitBreaker>>>,
    retry_mechanism: RetryMechanism,
    message_batcher: Option<MessageBatcher>,
    compressor: MessageCompressor,
    config: FailoverConfig,
}

/// Failover manager configuration
#[derive(Debug, Clone)]
pub struct FailoverConfig {
    pub circuit_breaker: CircuitBreakerConfig,
    pub retry: RetryConfig,
    pub batch: Option<BatchConfig>,
    pub performance: PerformanceConfig,
    pub enable_graceful_degradation: bool,
    pub health_check_interval: Duration,
}

impl Default for FailoverConfig {
    fn default() -> Self {
        Self {
            circuit_breaker: CircuitBreakerConfig::default(),
            retry: RetryConfig::default(),
            batch: Some(BatchConfig::default()),
            performance: PerformanceConfig::default(),
            enable_graceful_degradation: true,
            health_check_interval: Duration::from_secs(30),
        }
    }
}

impl FailoverManager {
    /// Create a new failover manager
    pub fn new(config: FailoverConfig) -> Self {
        let message_batcher = config.batch.as_ref().map(|batch_config| {
            MessageBatcher::new(batch_config.clone())
        });
        
        Self {
            circuit_breakers: Arc::new(RwLock::new(HashMap::new())),
            retry_mechanism: RetryMechanism::new(config.retry.clone()),
            message_batcher,
            compressor: MessageCompressor::new(config.performance.clone()),
            config,
        }
    }
    
    /// Execute an operation with full failover protection
    pub async fn execute_with_failover<F, Fut, T>(
        &self,
        channel_type: ChannelType,
        operation: F,
    ) -> Result<T, MessageError>
    where
        F: Fn() -> Fut + Clone,
        Fut: std::future::Future<Output = Result<T, MessageError>>,
    {
        // Get or create circuit breaker for this channel
        let circuit_breaker = {
            let mut breakers = self.circuit_breakers.write().unwrap();
            breakers.entry(channel_type)
                .or_insert_with(|| CircuitBreaker::new(self.config.circuit_breaker.clone()))
                .clone()
        };
        
        // Check circuit breaker
        if !circuit_breaker.can_execute().await {
            return Err(MessageError::InvalidFormat(
                format!("Circuit breaker open for {:?}", channel_type)
            ));
        }
        
        // Execute with retry mechanism
        let result = self.retry_mechanism.execute(move || {
            let op = operation.clone();
            async move { op().await }
        }).await;
        
        // Record result in circuit breaker
        match &result {
            Ok(_) => circuit_breaker.record_success().await,
            Err(_) => circuit_breaker.record_failure().await,
        }
        
        result
    }
    
    /// Send a message with batching if enabled
    pub async fn send_with_batching(&self, message: EncodedMessage) -> Result<(), MessageError> {
        if let Some(batcher) = &self.message_batcher {
            batcher.add_message(message).await
        } else {
            Err(MessageError::InvalidFormat("Batching not enabled".to_string()))
        }
    }
    
    /// Flush any pending batched messages
    pub async fn flush_batches(&self) -> Result<(), MessageError> {
        if let Some(batcher) = &self.message_batcher {
            batcher.flush().await
        } else {
            Ok(())
        }
    }
    
    /// Get circuit breaker statistics for all channels
    pub fn get_circuit_breaker_stats(&self) -> HashMap<ChannelType, CircuitBreakerStats> {
        let breakers = self.circuit_breakers.read().unwrap();
        breakers.iter()
            .map(|(&channel, breaker)| (channel, breaker.get_stats()))
            .collect()
    }
    
    /// Manually trigger circuit breaker state change
    pub async fn set_circuit_breaker_state(&self, channel: ChannelType, state: CircuitBreakerState) {
        let breakers = self.circuit_breakers.read().unwrap();
        if let Some(breaker) = breakers.get(&channel) {
            match state {
                CircuitBreakerState::Open => breaker.transition_to_open().await,
                CircuitBreakerState::HalfOpen => breaker.transition_to_half_open().await,
                CircuitBreakerState::Closed => breaker.transition_to_closed().await,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::time::sleep;
    
    #[tokio::test]
    async fn test_circuit_breaker() {
        let config = CircuitBreakerConfig {
            failure_threshold: 2,
            success_threshold: 1,
            timeout: Duration::from_millis(100),
            minimum_requests: 2,
            ..Default::default()
        };
        
        let breaker = CircuitBreaker::new(config);
        
        // Initial state should be closed
        assert_eq!(breaker.get_state(), CircuitBreakerState::Closed);
        assert!(breaker.can_execute().await);
        
        // Record failures
        breaker.record_failure().await;
        breaker.record_failure().await;
        
        // Should transition to open
        assert_eq!(breaker.get_state(), CircuitBreakerState::Open);
        assert!(!breaker.can_execute().await);
        
        // Wait for timeout
        sleep(Duration::from_millis(150)).await;
        
        // Should allow execution (half-open)
        assert!(breaker.can_execute().await);
        assert_eq!(breaker.get_state(), CircuitBreakerState::HalfOpen);
        
        // Record success to close circuit
        breaker.record_success().await;
        assert_eq!(breaker.get_state(), CircuitBreakerState::Closed);
    }
    
    #[tokio::test]
    async fn test_retry_mechanism() {
        let config = RetryConfig {
            max_attempts: 3,
            base_delay: Duration::from_millis(1),
            ..Default::default()
        };
        
        let retry = RetryMechanism::new(config);
        let mut attempt_count = 0;
        
        let result = retry.execute(|| {
            attempt_count += 1;
            async move {
                if attempt_count < 3 {
                    Err("failure")
                } else {
                    Ok("success")
                }
            }
        }).await;
        
        assert_eq!(result, Ok("success"));
        assert_eq!(attempt_count, 3);
    }
    
    #[tokio::test]
    async fn test_message_batching() {
        let config = BatchConfig {
            max_batch_size: 3,
            max_batch_delay: Duration::from_millis(100),
            ..Default::default()
        };
        
        let batcher = MessageBatcher::new(config);
        
        // Add messages
        for i in 0..2 {
            let message = EncodedMessage::new(
                format!("message {}", i).into_bytes(), 
                crate::message::EncodingFormat::Json
            );
            batcher.add_message(message).await.unwrap();
        }
        
        // Should not have a batch yet
        let batch_result = timeout(Duration::from_millis(10), batcher.receive_batch()).await;
        assert!(batch_result.is_err());
        
        // Add one more message to trigger batch
        let message = EncodedMessage::new(b"message 2".to_vec(), crate::message::EncodingFormat::Json);
        batcher.add_message(message).await.unwrap();
        
        // Should have a batch now
        let batch = batcher.receive_batch().await.unwrap();
        assert_eq!(batch.len(), 3);
    }
    
    #[test]
    fn test_message_compression() {
        let config = PerformanceConfig {
            compression_threshold: 10,
            ..Default::default()
        };
        let compressor = MessageCompressor::new(config);
        
        // Create a large message
        let large_data = vec![b'a'; 1000];
        let mut message = EncodedMessage::new(large_data, crate::message::EncodingFormat::Json);
        let original_size = message.data().len();
        
        // Compress
        let was_compressed = compressor.compress_message(&mut message).unwrap();
        
        #[cfg(feature = "advanced_failover")]
        {
            // With advanced_failover feature, compression should work
            assert!(was_compressed);
            assert!(message.data().len() < original_size);
            
            // Decompress
            compressor.decompress_message(&mut message).unwrap();
            assert_eq!(message.data().len(), original_size);
        }
        
        #[cfg(not(feature = "advanced_failover"))]
        {
            // Without advanced_failover feature, compression should be disabled
            assert!(!was_compressed);
            assert_eq!(message.data().len(), original_size);
            
            // Decompression should fail
            assert!(compressor.decompress_message(&mut message).is_err());
        }
    }
} 