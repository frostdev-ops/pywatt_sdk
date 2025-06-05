//! Port negotiation utilities for PyWatt modules.
//!
//! This module provides an improved implementation of the port negotiation mechanism
//! used by PyWatt modules to request and allocate ports for HTTP servers.

use crate::ipc_types::{IpcPortNegotiation, IpcPortNegotiationResponse, ModuleToOrchestrator};
use std::net::{IpAddr, SocketAddr};
use std::str::FromStr;
use std::sync::{Mutex as StdMutex};
use tokio::io::{self, AsyncWriteExt};
use tokio::sync::oneshot;
use tokio::time::{Duration, timeout, Instant};
use tracing::{debug, error, info, warn, trace};
use uuid::Uuid;
use rand;
use serde_json;

/// Port for the negotiation service.
/// This is the initial port where modules connect to negotiate their actual working port.
pub const NEGOTIATION_PORT: u16 = 9998;

/// Maximum port in the range for port allocation
pub const MAX_PORT: u16 = 65535;

/// Minimum port in the dynamic range 
pub const MIN_DYNAMIC_PORT: u16 = 49152;

/// Default timeout for port negotiation in seconds
const DEFAULT_PORT_NEGOTIATION_TIMEOUT_SECS: u64 = 3;

/// Initial timeout for port negotiation in seconds
const INITIAL_PORT_NEGOTIATION_TIMEOUT_SECS: u64 = 3;

/// Maximum timeout for port negotiation in seconds
const MAX_PORT_NEGOTIATION_TIMEOUT_SECS: u64 = 10;

/// Maximum retry attempts for port negotiation
const MAX_PORT_NEGOTIATION_RETRIES: u8 = 3;

/// Default port range for random port selection (if requested port is unavailable)
const DEFAULT_PORT_RANGE_START: u16 = 8000;
const DEFAULT_PORT_RANGE_END: u16 = 9000;

/// Circuit breaker threshold - after this many consecutive failures, 
/// the circuit breaker opens and we use fallback mechanisms
const CIRCUIT_BREAKER_THRESHOLD: u8 = 5;

/// Circuit breaker reset time in seconds - after this time we'll try normal operation again
const CIRCUIT_BREAKER_RESET_SECS: u64 = 60; // 1 minute

/// Fallback port range for generating unique ports when orchestrator communication fails
const FALLBACK_PORT_RANGE_START: u16 = 10000;
const FALLBACK_PORT_RANGE_END: u16 = 11000;

// Global variables for port negotiation
lazy_static::lazy_static! {
    static ref ALLOCATED_PORT: StdMutex<Option<u16>> = StdMutex::new(None);
    
    // Global port negotiation response channel
    static ref PORT_RESPONSE_CHANNEL: StdMutex<Option<oneshot::Sender<IpcPortNegotiationResponse>>> = {
        StdMutex::new(None)
    };
    
    // Global port negotiation state
    static ref PORT_NEGOTIATION_STATE: StdMutex<PortNegotiationState> = {
        StdMutex::new(PortNegotiationState::default())
    };
    
    // Global mutex-wrapped stdout for sending messages to the orchestrator
    static ref STDOUT_WRITER: tokio::sync::Mutex<io::Stdout> = tokio::sync::Mutex::new(io::stdout());
    
    // Circuit breaker state
    static ref CIRCUIT_BREAKER: StdMutex<CircuitBreakerState> = {
        StdMutex::new(CircuitBreakerState::default())
    };
}

/// Circuit breaker state
#[derive(Debug, Clone)]
enum CircuitBreakerStatus {
    /// Circuit is closed, normal operation
    Closed,
    /// Circuit is open, using fallback mechanisms
    Open,
    /// Circuit is half-open, testing if normal operation can resume
    HalfOpen,
}

impl Default for CircuitBreakerStatus {
    fn default() -> Self {
        CircuitBreakerStatus::Closed
    }
}

/// Circuit breaker state
#[derive(Debug, Clone)]
struct CircuitBreakerState {
    /// Current status of the circuit breaker
    status: CircuitBreakerStatus,
    /// Number of consecutive failures
    failure_count: u8,
    /// Timestamp when the circuit was opened
    opened_at: Option<Instant>,
    /// Timestamp of the last attempt to close the circuit
    last_attempt: Option<Instant>,
}

impl Default for CircuitBreakerState {
    fn default() -> Self {
        Self {
            status: CircuitBreakerStatus::default(),
            failure_count: 0,
            opened_at: None,
            last_attempt: None,
        }
    }
}

/// Port negotiation state
#[derive(Debug, Clone, Default)]
struct PortNegotiationState {
    /// The current negotiation request ID, if any
    current_request_id: Option<String>,
    
    /// Number of retry attempts for the current request
    retry_count: u8,
    
    /// Timestamp of the last attempt
    last_attempt_timestamp: Option<Instant>,
    
    /// Whether a negotiation is in progress
    in_progress: bool,
    
    /// Current timeout duration in seconds
    current_timeout_secs: u64,
    
    /// Diagnostic information about failures
    failure_diagnostics: Vec<String>,
}

/// Socket address validation error
#[derive(Debug, Clone)]
pub enum SocketAddressError {
    /// Invalid format
    InvalidFormat(String),
    /// Invalid IP address
    InvalidIpAddress(String),
    /// Invalid port
    InvalidPort(String),
}

impl std::fmt::Display for SocketAddressError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SocketAddressError::InvalidFormat(msg) => write!(f, "Invalid socket address format: {}", msg),
            SocketAddressError::InvalidIpAddress(msg) => write!(f, "Invalid IP address: {}", msg),
            SocketAddressError::InvalidPort(msg) => write!(f, "Invalid port: {}", msg),
        }
    }
}

/// Result of a port negotiation attempt
#[derive(Debug, Clone)]
pub enum PortNegotiationResult {
    /// Port was successfully allocated
    Success(u16),
    
    /// Port negotiation failed
    Failure {
        /// Error message
        message: String,
        /// Detailed diagnostic information
        diagnostics: Vec<String>,
    },
    
    /// Port negotiation timed out
    Timeout {
        /// Number of seconds that elapsed before timeout
        elapsed_secs: u64,
        /// Request ID
        request_id: String,
    },
    
    /// Using fallback port due to persistent failures
    UsingFallback {
        /// Fallback port
        port: u16,
        /// Reason for using fallback
        reason: String,
    },
}

impl PortNegotiationResult {
    /// Get a human-readable message describing the result
    pub fn to_message(&self) -> String {
        match self {
            Self::Success(port) => format!("Port {} successfully allocated", port),
            Self::Failure { message, diagnostics } => {
                if diagnostics.is_empty() {
                    message.clone()
                } else {
                    format!("{} ({})", message, diagnostics.join(", "))
                }
            },
            Self::Timeout { elapsed_secs, request_id } => {
                format!("Port negotiation timed out after {}s (request_id={})", elapsed_secs, request_id)
            },
            Self::UsingFallback { port, reason } => {
                format!("Using fallback port {}: {}", port, reason)
            },
        }
    }
    
    /// Get the allocated port if successful or using fallback
    pub fn port(&self) -> Option<u16> {
        match self {
            Self::Success(port) => Some(*port),
            Self::UsingFallback { port, .. } => Some(*port),
            _ => None,
        }
    }
    
    /// Whether the result represents a successful port allocation
    pub fn is_success(&self) -> bool {
        matches!(self, Self::Success(_) | Self::UsingFallback { .. })
    }
    
    /// Whether the result represents a failure
    pub fn is_failure(&self) -> bool {
        matches!(self, Self::Failure { .. } | Self::Timeout { .. })
    }
    
    /// Whether the result is using a fallback port
    pub fn is_fallback(&self) -> bool {
        matches!(self, Self::UsingFallback { .. })
    }
}

/// Port negotiation manager
pub struct PortNegotiationManager {
    /// Configuration for timeouts and retries
    config: PortNegotiationConfig,
}

/// Configuration for port negotiation
#[derive(Debug, Clone)]
pub struct PortNegotiationConfig {
    /// Initial timeout in seconds
    pub initial_timeout_secs: u64,
    /// Maximum timeout in seconds
    pub max_timeout_secs: u64,
    /// Maximum number of retry attempts
    pub max_retries: u8,
    /// Whether to use fallback ports when negotiation fails
    pub use_fallback: bool,
    /// Custom fallback port to use
    pub custom_fallback_port: Option<u16>,
    /// Port range start for random port selection
    pub port_range_start: u16,
    /// Port range end for random port selection
    pub port_range_end: u16,
}

impl Default for PortNegotiationConfig {
    fn default() -> Self {
        Self {
            initial_timeout_secs: INITIAL_PORT_NEGOTIATION_TIMEOUT_SECS,
            max_timeout_secs: MAX_PORT_NEGOTIATION_TIMEOUT_SECS,
            max_retries: MAX_PORT_NEGOTIATION_RETRIES,
            use_fallback: true,
            custom_fallback_port: None,
            port_range_start: DEFAULT_PORT_RANGE_START,
            port_range_end: DEFAULT_PORT_RANGE_END,
        }
    }
}

impl PortNegotiationManager {
    /// Create a new port negotiation manager with default configuration
    pub fn new() -> Self {
        Self {
            config: PortNegotiationConfig::default(),
        }
    }
    
    /// Create a new port negotiation manager with custom configuration
    pub fn with_config(config: PortNegotiationConfig) -> Self {
        Self { config }
    }
    
    /// Validate a socket address string
    pub fn validate_socket_address(addr_str: &str) -> Result<SocketAddr, SocketAddressError> {
        // Try to parse as a socket address
        match SocketAddr::from_str(addr_str) {
            Ok(addr) => {
                // Validate IP address
                match addr.ip() {
                    IpAddr::V4(ipv4) => {
                        if ipv4.is_unspecified() || ipv4.is_broadcast() {
                            return Err(SocketAddressError::InvalidIpAddress(
                                "IP address cannot be unspecified (0.0.0.0) or broadcast".to_string()
                            ));
                        }
                    },
                    IpAddr::V6(ipv6) => {
                        if ipv6.is_unspecified() {
                            return Err(SocketAddressError::InvalidIpAddress(
                                "IP address cannot be unspecified (::)".to_string()
                            ));
                        }
                    }
                }
                
                // Validate port
                if addr.port() == 0 {
                    return Err(SocketAddressError::InvalidPort("Port cannot be 0".to_string()));
                }
                
                Ok(addr)
            },
            Err(e) => Err(SocketAddressError::InvalidFormat(e.to_string())),
        }
    }
    
    /// Format a socket address from an IP and port
    pub fn format_socket_address(ip: &str, port: u16) -> Result<String, SocketAddressError> {
        // Parse the IP address
        let ip_addr = match IpAddr::from_str(ip) {
            Ok(addr) => addr,
            Err(e) => return Err(SocketAddressError::InvalidIpAddress(e.to_string())),
        };
        
        // Validate the port
        if port == 0 {
            return Err(SocketAddressError::InvalidPort("Port cannot be 0".to_string()));
        }
        
        // Format the socket address
        let socket_addr = SocketAddr::new(ip_addr, port);
        Ok(socket_addr.to_string())
    }
    
    /// Get the circuit breaker state
    fn check_circuit_breaker(&self) -> Result<CircuitBreakerStatus, String> {
        let mut breaker = CIRCUIT_BREAKER.lock().map_err(|e| format!("Failed to lock CIRCUIT_BREAKER: {}", e))?;
        
        match breaker.status {
            CircuitBreakerStatus::Closed => {
                // Normal operation
                Ok(CircuitBreakerStatus::Closed)
            },
            CircuitBreakerStatus::Open => {
                // Check if it's time to try closing the circuit
                if let Some(opened_at) = breaker.opened_at {
                    let elapsed = opened_at.elapsed();
                    if elapsed >= Duration::from_secs(CIRCUIT_BREAKER_RESET_SECS) {
                        // Try half-open state
                        breaker.status = CircuitBreakerStatus::HalfOpen;
                        breaker.last_attempt = Some(Instant::now());
                        info!("Circuit breaker transitioning to half-open state after {} seconds", elapsed.as_secs());
                        Ok(CircuitBreakerStatus::HalfOpen)
                    } else {
                        // Still open
                        let remaining = CIRCUIT_BREAKER_RESET_SECS.saturating_sub(elapsed.as_secs());
                        debug!("Circuit breaker still open, {} seconds remaining until retry", remaining);
                        Ok(CircuitBreakerStatus::Open)
                    }
                } else {
                    // No opened_at timestamp, reset to closed
                    breaker.status = CircuitBreakerStatus::Closed;
                    breaker.failure_count = 0;
                    Ok(CircuitBreakerStatus::Closed)
                }
            },
            CircuitBreakerStatus::HalfOpen => {
                // We're testing if normal operation can resume
                Ok(CircuitBreakerStatus::HalfOpen)
            }
        }
    }
    
    /// Record a success in the circuit breaker
    fn record_success(&self) -> Result<(), String> {
        let mut breaker = CIRCUIT_BREAKER.lock().map_err(|e| format!("Failed to lock CIRCUIT_BREAKER: {}", e))?;
        
        match breaker.status {
            CircuitBreakerStatus::Closed => {
                // Reset failure count on success
                breaker.failure_count = 0;
            },
            CircuitBreakerStatus::HalfOpen => {
                // If we succeed in half-open state, close the circuit
                info!("Circuit breaker closed after successful operation in half-open state");
                breaker.status = CircuitBreakerStatus::Closed;
                breaker.failure_count = 0;
                breaker.opened_at = None;
            },
            CircuitBreakerStatus::Open => {
                // This shouldn't happen, but just in case
                breaker.status = CircuitBreakerStatus::Closed;
                breaker.failure_count = 0;
                breaker.opened_at = None;
            }
        }
        
        Ok(())
    }
    
    /// Record a failure in the circuit breaker
    fn record_failure(&self) -> Result<CircuitBreakerStatus, String> {
        let mut breaker = CIRCUIT_BREAKER.lock().map_err(|e| format!("Failed to lock CIRCUIT_BREAKER: {}", e))?;
        
        match breaker.status {
            CircuitBreakerStatus::Closed => {
                // Increment failure count
                breaker.failure_count += 1;
                
                // Check if we've reached the threshold
                if breaker.failure_count >= CIRCUIT_BREAKER_THRESHOLD {
                    // Open the circuit
                    breaker.status = CircuitBreakerStatus::Open;
                    breaker.opened_at = Some(Instant::now());
                    warn!("Circuit breaker opened after {} consecutive failures", breaker.failure_count);
                }
            },
            CircuitBreakerStatus::HalfOpen => {
                // If we fail in half-open state, go back to open
                breaker.status = CircuitBreakerStatus::Open;
                breaker.opened_at = Some(Instant::now());
                warn!("Circuit breaker reopened after failure in half-open state");
            },
            CircuitBreakerStatus::Open => {
                // Already open, nothing to do
            }
        }
        
        Ok(breaker.status.clone())
    }

    /// Request a port from the orchestrator with detailed diagnostics
    /// 
    /// # Arguments
    /// * `specific_port` - Optional specific port to request
    /// * `timeout_secs` - Optional timeout in seconds (defaults to configured value)
    /// 
    /// # Returns
    /// A detailed result of the port negotiation
    pub async fn request_port_with_diagnostics(
        &self, 
        specific_port: Option<u16>,
        timeout_secs: Option<u64>
    ) -> PortNegotiationResult {
        // Check if we already have an allocated port
        {
            let port_guard = match ALLOCATED_PORT.lock() {
                Ok(guard) => guard,
                Err(e) => {
                    return PortNegotiationResult::Failure {
                        message: format!("Failed to lock ALLOCATED_PORT: {}", e),
                        diagnostics: vec![format!("Lock error: {}", e)],
                    };
                }
            };
            
            if let Some(port) = *port_guard {
                info!("Port already allocated: {}", port);
                return PortNegotiationResult::Success(port);
            }
        }
        
        // Check circuit breaker state
        let cb_status = match self.check_circuit_breaker() {
            Ok(status) => status,
            Err(e) => {
                return PortNegotiationResult::Failure {
                    message: format!("Failed to check circuit breaker state: {}", e),
                    diagnostics: vec![format!("Circuit breaker error: {}", e)],
                };
            }
        };
        
        match cb_status {
            CircuitBreakerStatus::Open => {
                // Circuit is open, use fallback port
                if self.config.use_fallback {
                    let fallback_port = if let Some(custom) = self.config.custom_fallback_port {
                        custom
                    } else {
                        // Generate a random port in the fallback range
                        let range = FALLBACK_PORT_RANGE_END - FALLBACK_PORT_RANGE_START;
                        FALLBACK_PORT_RANGE_START + (rand::random::<u16>() % range)
                    };
                    
                    // Store the fallback port
                    {
                        let mut port_guard = match ALLOCATED_PORT.lock() {
                            Ok(guard) => guard,
                            Err(e) => {
                                return PortNegotiationResult::Failure {
                                    message: format!("Failed to lock ALLOCATED_PORT: {}", e),
                                    diagnostics: vec![
                                        format!("Circuit breaker status: {:?}", cb_status),
                                        format!("Using fallback port: {}", fallback_port),
                                        format!("Lock error: {}", e)
                                    ],
                                };
                            }
                        };
                        *port_guard = Some(fallback_port);
                    }
                    
                    warn!("Using fallback port {} due to open circuit breaker", fallback_port);
                    return PortNegotiationResult::UsingFallback {
                        port: fallback_port,
                        reason: "Circuit breaker is open due to persistent failures".to_string(),
                    };
                } else {
                    warn!("Circuit breaker is open but fallback ports are disabled");
                }
            },
            CircuitBreakerStatus::HalfOpen => {
                debug!("Circuit breaker is half-open, attempting normal operation");
            },
            CircuitBreakerStatus::Closed => {
                debug!("Circuit breaker is closed, proceeding with normal operation");
            }
        }
        
        // Set timeout based on retry count and configuration
        let timeout_duration = {
            let state = match PORT_NEGOTIATION_STATE.lock() {
                Ok(guard) => guard,
                Err(e) => {
                    return PortNegotiationResult::Failure {
                        message: format!("Failed to lock PORT_NEGOTIATION_STATE: {}", e),
                        diagnostics: vec![format!("Lock error: {}", e)],
                    };
                }
            };
            
            let timeout_secs = timeout_secs.unwrap_or_else(|| {
                if state.retry_count == 0 {
                    self.config.initial_timeout_secs
                } else {
                    // Linear backoff instead of exponential to avoid huge timeouts
                    let backoff = self.config.initial_timeout_secs + (state.retry_count as u64);
                    std::cmp::min(backoff, self.config.max_timeout_secs)
                }
            });
            
            Duration::from_secs(timeout_secs)
        };
        
        // Generate a unique request ID
        let request_id = Uuid::new_v4().to_string();
        
        // Update negotiation state
        {
            let mut state = match PORT_NEGOTIATION_STATE.lock() {
                Ok(guard) => guard,
                Err(e) => {
                    return PortNegotiationResult::Failure {
                        message: format!("Failed to lock PORT_NEGOTIATION_STATE: {}", e),
                        diagnostics: vec![format!("Lock error: {}", e)],
                    };
                }
            };
            
            state.current_request_id = Some(request_id.clone());
            state.last_attempt_timestamp = Some(Instant::now());
            state.in_progress = true;
            state.current_timeout_secs = timeout_duration.as_secs();
            
            // Clear previous diagnostics if this is a new request (not a retry)
            if state.retry_count == 0 {
                state.failure_diagnostics.clear();
            }
            
            debug!("Starting port negotiation (request_id={}, specific_port={:?}, timeout={}s, attempt={}/{})", 
                   request_id, specific_port, timeout_duration.as_secs(), 
                   state.retry_count + 1, self.config.max_retries);
        }
        
        // Prepare the port negotiation request
        let request = IpcPortNegotiation {
            request_id: request_id.clone(),
            specific_port,
        };
        
        // Create a channel for receiving the response
        let (tx, rx) = oneshot::channel();
        
        // Store the sender for later use
        {
            let mut port_sender = match PORT_RESPONSE_CHANNEL.lock() {
                Ok(guard) => guard,
                Err(e) => {
                    return PortNegotiationResult::Failure {
                        message: format!("Failed to lock PORT_RESPONSE_CHANNEL: {}", e),
                        diagnostics: vec![format!("Lock error: {}", e)],
                    };
                }
            };
            *port_sender = Some(tx);
        }
        
        // Send the request
        let start_time = Instant::now();
        match self.send_port_request(&request).await {
            Ok(_) => {
                trace!("Port request sent successfully, waiting for response (timeout={}s)", timeout_duration.as_secs());
            },
            Err(e) => {
                // Record failure in circuit breaker
                let _ = self.record_failure();
                
                // Update negotiation state
                {
                    let mut state = match PORT_NEGOTIATION_STATE.lock() {
                        Ok(guard) => guard,
                        Err(lock_err) => {
                            return PortNegotiationResult::Failure {
                                message: format!("Failed to lock PORT_NEGOTIATION_STATE: {}", lock_err),
                                diagnostics: vec![
                                    format!("Request sending error: {}", e),
                                    format!("Lock error: {}", lock_err)
                                ],
                            };
                        }
                    };
                    state.in_progress = false;
                    state.failure_diagnostics.push(format!("Failed to send request: {}", e));
                }
                
                return PortNegotiationResult::Failure {
                    message: format!("Failed to send port request: {}", e),
                    diagnostics: vec![format!("Request sending error: {}", e)],
                };
            }
        }
        
        // Wait for the response with a timeout
        match timeout(timeout_duration, rx).await {
            Ok(Ok(response)) => {
                let elapsed = start_time.elapsed();
                debug!("Received port response after {}ms", elapsed.as_millis());
                
                // Update negotiation state
                {
                    let mut state = match PORT_NEGOTIATION_STATE.lock() {
                        Ok(guard) => guard,
                        Err(e) => {
                            return PortNegotiationResult::Failure {
                                message: format!("Failed to lock PORT_NEGOTIATION_STATE: {}", e),
                                diagnostics: vec![format!("Lock error: {}", e)],
                            };
                        }
                    };
                    state.in_progress = false;
                }
                
                if response.success {
                    info!("Port negotiation successful (request_id={}, port={}, took={}ms)", 
                          request_id, response.port, elapsed.as_millis());
                    
                    // Record success in circuit breaker
                    let _ = self.record_success();
                    
                    // Store the allocated port
                    {
                        let mut port_guard = match ALLOCATED_PORT.lock() {
                            Ok(guard) => guard,
                            Err(e) => {
                                return PortNegotiationResult::Failure {
                                    message: format!("Failed to lock ALLOCATED_PORT: {}", e),
                                    diagnostics: vec![format!("Lock error: {}", e)],
                                };
                            }
                        };
                        *port_guard = Some(response.port);
                    }
                    
                    PortNegotiationResult::Success(response.port)
                } else {
                    let error_msg = response.error_message.unwrap_or_else(|| "Unknown error".to_string());
                    error!("Port negotiation failed: {} (request_id={})", error_msg, request_id);
                    
                    // Record failure in circuit breaker
                    let _ = self.record_failure();
                    
                    // Update diagnostics
                    {
                        let mut state = match PORT_NEGOTIATION_STATE.lock() {
                            Ok(guard) => guard,
                            Err(e) => {
                                return PortNegotiationResult::Failure {
                                    message: format!("Failed to lock PORT_NEGOTIATION_STATE after receiving error: {}", e),
                                    diagnostics: vec![
                                        format!("Orchestrator error: {}", error_msg),
                                        format!("Lock error: {}", e)
                                    ],
                                };
                            }
                        };
                        state.failure_diagnostics.push(format!("Orchestrator error: {}", error_msg));
                    }
                    
                    PortNegotiationResult::Failure {
                        message: format!("Port negotiation failed: {}", error_msg),
                        diagnostics: vec![format!("Orchestrator error: {}", error_msg)],
                    }
                }
            },
            Ok(Err(_)) => {
                // The sender was dropped
                error!("Port negotiation sender was dropped (request_id={})", request_id);
                
                // Record failure in circuit breaker
                let _ = self.record_failure();
                
                // Update negotiation state
                {
                    let mut state = match PORT_NEGOTIATION_STATE.lock() {
                        Ok(guard) => guard,
                        Err(e) => {
                            return PortNegotiationResult::Failure {
                                message: format!("Failed to lock PORT_NEGOTIATION_STATE: {}", e),
                                diagnostics: vec![
                                    "Response channel was closed".to_string(),
                                    format!("Lock error: {}", e)
                                ],
                            };
                        }
                    };
                    state.in_progress = false;
                    state.failure_diagnostics.push("Response channel was closed".to_string());
                }
                
                PortNegotiationResult::Failure {
                    message: "Port negotiation failed: response channel was closed".to_string(),
                    diagnostics: vec!["Response channel was closed".to_string()],
                }
            },
            Err(_) => {
                // Timeout occurred
                let elapsed = start_time.elapsed();
                warn!("Port negotiation timed out after {}ms (request_id={})", 
                      elapsed.as_millis(), request_id);
                
                // Record failure in circuit breaker
                let cb_status = match self.record_failure() {
                    Ok(status) => status,
                    Err(e) => {
                        return PortNegotiationResult::Failure {
                            message: format!("Failed to update circuit breaker after timeout: {}", e),
                            diagnostics: vec![
                                format!("Timeout after {}ms", elapsed.as_millis()),
                                format!("Circuit breaker error: {}", e)
                            ],
                        };
                    }
                };
                
                // Update negotiation state for potential retry
                let should_retry = {
                    let mut state = match PORT_NEGOTIATION_STATE.lock() {
                        Ok(guard) => guard,
                        Err(e) => {
                            return PortNegotiationResult::Failure {
                                message: format!("Failed to lock PORT_NEGOTIATION_STATE after timeout: {}", e),
                                diagnostics: vec![
                                    format!("Timeout after {}ms", elapsed.as_millis()),
                                    format!("Lock error: {}", e)
                                ],
                            };
                        }
                    };
                    
                    state.retry_count += 1;
                    state.failure_diagnostics.push(format!("Timeout after {}ms", elapsed.as_millis()));
                    
                    let should_retry = state.retry_count < self.config.max_retries;
                    if !should_retry {
                        state.in_progress = false;
                    }
                    
                    should_retry
                };
                
                if should_retry {
                    // We'll attempt a retry with a random port in the configured range
                    let random_port = if specific_port.is_none() {
                        Some(self.config.port_range_start + 
                             (rand::random::<u16>() % (self.config.port_range_end - self.config.port_range_start)))
                    } else {
                        None // Keep the specific port if it was requested
                    };
                    
                    info!("Retrying port negotiation with {}port (attempt {}/{})", 
                          random_port.map_or("same ".to_string(), |p| format!("random port {} ", p)),
                          {
                              let state = PORT_NEGOTIATION_STATE.lock().unwrap();
                              state.retry_count + 1
                          }, 
                          self.config.max_retries);
                    
                    // Recursive call for retry
                    // Must use Box::pin to avoid infinitely sized future with recursive async fn
                    Box::pin(self.request_port_with_diagnostics(random_port, None)).await
                } else if matches!(cb_status, CircuitBreakerStatus::Open) && self.config.use_fallback {
                    // Circuit breaker is open and we've exhausted retries, use fallback port
                    let fallback_port = if let Some(custom) = self.config.custom_fallback_port {
                        custom
                    } else {
                        // Generate a random port in the fallback range
                        let range = FALLBACK_PORT_RANGE_END - FALLBACK_PORT_RANGE_START;
                        FALLBACK_PORT_RANGE_START + (rand::random::<u16>() % range)
                    };
                    
                    warn!("Max retries ({}) reached and circuit breaker open, using fallback port {}", 
                          self.config.max_retries, fallback_port);
                    
                    // Store the fallback port
                    {
                        let mut port_guard = match ALLOCATED_PORT.lock() {
                            Ok(guard) => guard,
                            Err(e) => {
                                return PortNegotiationResult::Failure {
                                    message: format!("Failed to lock ALLOCATED_PORT: {}", e),
                                    diagnostics: vec![
                                        format!("Circuit breaker status: {:?}", cb_status),
                                        format!("Using fallback port: {}", fallback_port),
                                        format!("Lock error: {}", e)
                                    ],
                                };
                            }
                        };
                        *port_guard = Some(fallback_port);
                    }
                    
                    let _diagnostics = {
                        let mut diags = Vec::new();
                        diags.push(format!("Fallback port {} allocated", fallback_port));
                        diags.push(format!("Circuit breaker status: {:?}", cb_status));
                        
                        // More diagnostic info
                        if let Ok(cb_state) = CIRCUIT_BREAKER.lock() {
                            diags.push(format!("Failure count: {}", cb_state.failure_count));
                            if let Some(opened_at) = cb_state.opened_at {
                                diags.push(format!("Circuit opened {} seconds ago", opened_at.elapsed().as_secs()));
                            }
                        }
                        
                        diags
                    };
                    
                    PortNegotiationResult::UsingFallback {
                        port: fallback_port,
                        reason: format!("Max retries ({}) reached and circuit breaker open", self.config.max_retries),
                    }
                } else {
                    // No retry and no fallback, just return timeout error
                    // Get diagnostics from state
                    let diagnostics = {
                        let state = match PORT_NEGOTIATION_STATE.lock() {
                            Ok(guard) => guard,
                            Err(e) => {
                                return PortNegotiationResult::Timeout {
                                    elapsed_secs: elapsed.as_secs(),
                                    request_id,
                                };
                            }
                        };
                        state.failure_diagnostics.clone()
                    };
                    
                    PortNegotiationResult::Timeout {
                        elapsed_secs: elapsed.as_secs(),
                        request_id,
                    }
                }
            }
        }
    }
    
    /// Request a port from the orchestrator
    /// 
    /// # Arguments
    /// * `specific_port` - Optional specific port to request
    /// * `timeout_secs` - Optional timeout in seconds (defaults to 5)
    /// 
    /// # Returns
    /// A result containing the allocated port or an error
    pub async fn request_port(
        &self, 
        specific_port: Option<u16>,
        timeout_secs: Option<u64>
    ) -> Result<u16, String> {
        let result = self.request_port_with_diagnostics(specific_port, timeout_secs).await;
        
        // Log appropriate message based on result type
        match &result {
            PortNegotiationResult::Success(_) => {
                debug!("{}", result.to_message());
            },
            PortNegotiationResult::Failure { message, diagnostics } => {
                error!("Port negotiation failed: {} (diagnostics: {:?})", message, diagnostics);
            },
            PortNegotiationResult::Timeout { .. } => {
                warn!("{}", result.to_message());
            },
            PortNegotiationResult::UsingFallback { .. } => {
                warn!("{}", result.to_message());
            }
        }
        
        // Convert to standard Result type
        if let Some(port) = result.port() {
            Ok(port)
        } else {
            Err(result.to_message())
        }
    }
    
    /// Send a port negotiation request to the orchestrator
    async fn send_port_request(&self, request: &IpcPortNegotiation) -> Result<(), String> {
        let message = ModuleToOrchestrator::PortRequest(request.clone());
        let json = serde_json::to_string(&message).map_err(|e| format!("Failed to serialize port request: {}", e))?;
        
        info!("Sending port negotiation request to orchestrator: {}", json);
        
        // Send the message to the orchestrator
        let mut stdout_guard = STDOUT_WRITER.lock().await;
        
        let start = Instant::now();
        
        if let Err(e) = stdout_guard.write_all(json.as_bytes()).await {
            error!("Failed to write port request to stdout: {}", e);
            return Err(format!("Failed to write port request to stdout: {}", e));
        }
        
        if let Err(e) = stdout_guard.write_all(b"\n").await {
            error!("Failed to write newline after port request: {}", e);
            return Err(format!("Failed to write newline after port request: {}", e));
        }
        
        if let Err(e) = stdout_guard.flush().await {
            error!("Failed to flush stdout after port request: {}", e);
            return Err(format!("Failed to flush stdout after port request: {}", e));
        }
        
        let elapsed = start.elapsed();
        info!("Port negotiation request sent successfully (took {}ms)", elapsed.as_millis());
        
        Ok(())
    }
    
    /// Process a port negotiation response from the orchestrator
    pub fn process_port_response(response: IpcPortNegotiationResponse) -> Result<(), String> {
        info!("Processing port negotiation response: success={}, port={}, request_id={}", 
              response.success, response.port, response.request_id);
        
        // Check if we have a pending request
        let current_request_id = {
            let state = PORT_NEGOTIATION_STATE.lock().map_err(|e| format!("Failed to lock PORT_NEGOTIATION_STATE: {}", e))?;
            state.current_request_id.clone()
        };
        
        // Validate request ID if we have an ongoing negotiation
        if let Some(req_id) = current_request_id {
            if req_id != response.request_id && response.request_id != "auto-assigned" {
                warn!("Received port response with mismatched request ID: expected {}, got {}", 
                      req_id, response.request_id);
            } else {
                info!("Port response request ID matches: {}", req_id);
            }
        } else {
            warn!("Received port response but no pending request found");
        }
        
        // Validate the port if successful
        if response.success {
            if response.port == 0 {
                warn!("Received invalid port 0 in successful port response");
                
                // Try to send a modified response through the channel
                let modified_response = IpcPortNegotiationResponse {
                    success: false,
                    error_message: Some("Orchestrator returned invalid port 0".to_string()),
                    ..response.clone()
                };
                
                let port_sender = {
                    let mut guard = PORT_RESPONSE_CHANNEL.lock().map_err(|e| format!("Failed to lock PORT_RESPONSE_CHANNEL: {}", e))?;
                    guard.take()
                };
                
                if let Some(sender) = port_sender {
                    if sender.send(modified_response).is_err() {
                        warn!("Failed to send modified port response - receiver dropped");
                    }
                }
                
                return Err("Received invalid port 0 in successful port response".to_string());
            }
            
            let mut port_guard = ALLOCATED_PORT.lock().map_err(|e| format!("Failed to lock ALLOCATED_PORT: {}", e))?;
            *port_guard = Some(response.port);
            info!("Successfully allocated port: {}", response.port);
        } else {
            warn!("Port allocation failed: {:?}", response.error_message);
        }
        
        // Send the response through the oneshot channel if available
        let port_sender = {
            let mut guard = PORT_RESPONSE_CHANNEL.lock().map_err(|e| format!("Failed to lock PORT_RESPONSE_CHANNEL: {}", e))?;
            guard.take()
        };
        
        if let Some(sender) = port_sender {
            if sender.send(response.clone()).is_err() {
                warn!("Failed to send port response - receiver dropped");
            } else {
                info!("Port response sent to waiting receiver successfully");
            }
        } else {
            warn!("No waiting receiver for port response - this indicates a synchronization issue");
        }
        
        Ok(())
    }
    
    /// Get the currently allocated port, if any
    pub fn get_allocated_port() -> Option<u16> {
        ALLOCATED_PORT.lock().ok().and_then(|guard| *guard)
    }
    
    /// Get diagnostic information about port negotiation
    pub fn get_diagnostics() -> Result<Vec<String>, String> {
        let state = PORT_NEGOTIATION_STATE.lock().map_err(|e| format!("Failed to lock PORT_NEGOTIATION_STATE: {}", e))?;
        Ok(state.failure_diagnostics.clone())
    }
    
    /// Get the current port negotiation state for diagnostics
    pub fn get_negotiation_state() -> Result<String, String> {
        let state = PORT_NEGOTIATION_STATE.lock().map_err(|e| format!("Failed to lock PORT_NEGOTIATION_STATE: {}", e))?;
        let cb_state = CIRCUIT_BREAKER.lock().map_err(|e| format!("Failed to lock CIRCUIT_BREAKER: {}", e))?;
        
        let cb_status = match cb_state.status {
            CircuitBreakerStatus::Closed => "closed",
            CircuitBreakerStatus::Open => "open",
            CircuitBreakerStatus::HalfOpen => "half-open",
        };
        
        let state_json = serde_json::json!({
            "in_progress": state.in_progress,
            "current_request_id": state.current_request_id,
            "retry_count": state.retry_count,
            "last_attempt": state.last_attempt_timestamp.map(|t| t.elapsed().as_secs()),
            "timeout_secs": state.current_timeout_secs,
            "circuit_breaker": {
                "status": cb_status,
                "failure_count": cb_state.failure_count,
                "opened_at": cb_state.opened_at.map(|t| t.elapsed().as_secs()),
            },
            "allocated_port": Self::get_allocated_port(),
        });
        
        Ok(state_json.to_string())
    }
    
    /// Reset the port negotiation state (mainly for testing)
    #[cfg(test)]
    pub fn reset() {
        if let Ok(mut port_guard) = ALLOCATED_PORT.lock() {
            *port_guard = None;
        }
        
        if let Ok(mut state) = PORT_NEGOTIATION_STATE.lock() {
            *state = PortNegotiationState::default();
        }
        
        if let Ok(mut breaker) = CIRCUIT_BREAKER.lock() {
            *breaker = CircuitBreakerState::default();
        }
    }
    
    /// Try to recover the port negotiation system
    /// 
    /// This method attempts to recover the port negotiation system by:
    /// 1. Resetting internal state
    /// 2. Trying to obtain a port from the orchestrator
    /// 3. Falling back to a random port if orchestrator is unavailable
    pub async fn try_recover(&self) -> Result<u16, String> {
        info!("Attempting to recover port negotiation system");
        
        // Reset internal state
        {
            let mut state = PORT_NEGOTIATION_STATE.lock().map_err(|e| format!("Failed to lock PORT_NEGOTIATION_STATE: {}", e))?;
            state.current_request_id = None;
            state.retry_count = 0;
            state.last_attempt_timestamp = None;
            state.in_progress = false;
            state.failure_diagnostics.clear();
        }
        
        // Try to reset circuit breaker to half-open
        {
            let mut breaker = CIRCUIT_BREAKER.lock().map_err(|e| format!("Failed to lock CIRCUIT_BREAKER: {}", e))?;
            if matches!(breaker.status, CircuitBreakerStatus::Open) {
                breaker.status = CircuitBreakerStatus::HalfOpen;
                breaker.last_attempt = Some(Instant::now());
                info!("Reset circuit breaker to half-open state for recovery attempt");
            }
        }
        
        // Try to get a random port from the orchestrator
        let random_port = self.config.port_range_start + 
            (rand::random::<u16>() % (self.config.port_range_end - self.config.port_range_start));
        
        info!("Requesting random port {} for recovery", random_port);
        
        // Use a shorter timeout for recovery
        let recovery_timeout = std::cmp::min(self.config.initial_timeout_secs, 3);
        
        match self.request_port(Some(random_port), Some(recovery_timeout)).await {
            Ok(port) => {
                info!("Recovery successful, allocated port: {}", port);
                Ok(port)
            },
            Err(e) => {
                warn!("Recovery attempt failed: {}", e);
                
                if self.config.use_fallback {
                    // Use fallback port
                    let fallback_port = if let Some(custom) = self.config.custom_fallback_port {
                        custom
                    } else {
                        // Generate a random port in the fallback range
                        let range = FALLBACK_PORT_RANGE_END - FALLBACK_PORT_RANGE_START;
                        FALLBACK_PORT_RANGE_START + (rand::random::<u16>() % range)
                    };
                    
                    // Store the fallback port
                    {
                        let mut port_guard = match ALLOCATED_PORT.lock() {
                            Ok(guard) => guard,
                            Err(e) => {
                                return Err(format!("Failed to lock ALLOCATED_PORT: {}", e));
                            }
                        };
                        *port_guard = Some(fallback_port);
                    }
                    
                    warn!("Using fallback port {} after failed recovery attempt", fallback_port);
                    Ok(fallback_port)
                } else {
                    Err(format!("Recovery failed and fallback ports are disabled: {}", e))
                }
            }
        }
    }
    
    /// Test port negotiation functionality
    /// 
    /// This is a diagnostic function to test the port negotiation system
    pub async fn test_port_negotiation() -> Result<u16, String> {
        info!("Starting port negotiation diagnostic test");
        
        let manager = PortNegotiationManager::new();
        
        // Test basic port request
        info!("Testing basic port request (no specific port)");
        match manager.request_port_with_diagnostics(None, Some(5)).await {
            PortNegotiationResult::Success(port) => {
                info!("Port negotiation test successful: allocated port {}", port);
                Ok(port)
            },
            PortNegotiationResult::Failure { message, diagnostics } => {
                error!("Port negotiation test failed: {}", message);
                error!("Diagnostics: {:?}", diagnostics);
                Err(format!("Test failed: {}", message))
            },
            PortNegotiationResult::Timeout { elapsed_secs, request_id } => {
                error!("Port negotiation test timed out after {}s (request_id: {})", elapsed_secs, request_id);
                Err(format!("Test timed out after {}s", elapsed_secs))
            },
            PortNegotiationResult::UsingFallback { port, reason } => {
                warn!("Port negotiation test using fallback: port {}, reason: {}", port, reason);
                Ok(port)
            }
        }
    }
    
    /// Get comprehensive diagnostic information
    pub fn get_comprehensive_diagnostics() -> String {
        let mut diagnostics = Vec::new();
        
        // Port negotiation state
        match Self::get_negotiation_state() {
            Ok(state) => {
                diagnostics.push(format!("Port Negotiation State: {}", state));
            },
            Err(e) => {
                diagnostics.push(format!("Failed to get port negotiation state: {}", e));
            }
        }
        
        // Circuit breaker state
        if let Ok(cb_state) = CIRCUIT_BREAKER.lock() {
            let status = match cb_state.status {
                CircuitBreakerStatus::Closed => "closed",
                CircuitBreakerStatus::Open => "open",
                CircuitBreakerStatus::HalfOpen => "half-open",
            };
            diagnostics.push(format!("Circuit Breaker: status={}, failures={}", status, cb_state.failure_count));
        }
        
        // Allocated port
        if let Some(port) = Self::get_allocated_port() {
            diagnostics.push(format!("Currently allocated port: {}", port));
        } else {
            diagnostics.push("No port currently allocated".to_string());
        }
        
        // Failure diagnostics
        match Self::get_diagnostics() {
            Ok(failures) => {
                if !failures.is_empty() {
                    diagnostics.push(format!("Recent failures: {:?}", failures));
                }
            },
            Err(e) => {
                diagnostics.push(format!("Failed to get failure diagnostics: {}", e));
            }
        }
        
        diagnostics.join("\n")
    }
}

impl Default for PortNegotiationManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::test;
    
    #[test]
    async fn test_socket_address_validation() {
        // Valid addresses
        assert!(PortNegotiationManager::validate_socket_address("127.0.0.1:8080").is_ok());
        assert!(PortNegotiationManager::validate_socket_address("192.168.1.1:443").is_ok());
        assert!(PortNegotiationManager::validate_socket_address("[::1]:8080").is_ok());
        
        // Invalid addresses
        assert!(PortNegotiationManager::validate_socket_address("localhost:8080").is_err());
        assert!(PortNegotiationManager::validate_socket_address("127.0.0.1").is_err());
        assert!(PortNegotiationManager::validate_socket_address("127.0.0.1:").is_err());
        assert!(PortNegotiationManager::validate_socket_address("127.0.0.1:0").is_err());
        assert!(PortNegotiationManager::validate_socket_address("0.0.0.0:8080").is_err());
    }
    
    #[test]
    async fn test_format_socket_address() {
        // Valid combinations
        assert_eq!(PortNegotiationManager::format_socket_address("127.0.0.1", 8080).unwrap(), "127.0.0.1:8080");
        assert_eq!(PortNegotiationManager::format_socket_address("192.168.1.1", 443).unwrap(), "192.168.1.1:443");
        
        // Invalid combinations
        assert!(PortNegotiationManager::format_socket_address("localhost", 8080).is_err());
        assert!(PortNegotiationManager::format_socket_address("127.0.0.1", 0).is_err());
    }
    
    // More tests would be added here for circuit breaker, retry logic, etc.
}
