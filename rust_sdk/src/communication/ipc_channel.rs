//! IPC channel implementation for PyWatt modules.
//!
//! This module provides a Unix Domain Socket-based channel for communication between modules
//! and the orchestrator, offering high-performance local communication.

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::UnixStream;
use tokio::sync::Mutex;
use tokio::time::timeout as tokio_timeout;
use tracing::{debug, info, warn};

use crate::message::{EncodedMessage, MessageError, MessageResult};
use crate::tcp_types::{ConnectionState, NetworkError, NetworkResult, ReconnectPolicy};
use super::MessageChannel;

/// Configuration for an IPC connection using Unix Domain Sockets.
#[derive(Debug, Clone)]
pub struct IpcConnectionConfig {
    /// Path to the Unix Domain Socket
    pub socket_path: PathBuf,
    /// Timeout for connection attempts and operations
    pub timeout: Duration,
    /// Policy for reconnection attempts
    pub reconnect_policy: ReconnectPolicy,
}

impl Default for IpcConnectionConfig {
    fn default() -> Self {
        Self {
            socket_path: PathBuf::from("/tmp/pywatt.sock"),
            timeout: Duration::from_secs(5),
            reconnect_policy: ReconnectPolicy::ExponentialBackoff {
                initial_delay: Duration::from_millis(100),
                max_delay: Duration::from_secs(30),
                multiplier: 2.0,
            },
        }
    }
}

impl IpcConnectionConfig {
    /// Create a new IPC connection configuration.
    pub fn new<P: Into<PathBuf>>(socket_path: P) -> Self {
        Self {
            socket_path: socket_path.into(),
            ..Default::default()
        }
    }

    /// Set the timeout for connection attempts and operations.
    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    /// Set the reconnection policy.
    pub fn with_reconnect_policy(mut self, policy: ReconnectPolicy) -> Self {
        self.reconnect_policy = policy;
        self
    }
}

/// A Unix Domain Socket-based message channel.
#[derive(Debug)]
pub struct IpcChannel {
    /// Configuration for the connection.
    config: IpcConnectionConfig,
    /// The Unix stream, wrapped in a mutex for thread safety.
    stream: Arc<Mutex<Option<UnixStream>>>,
    /// Current state of the connection.
    state: Arc<Mutex<ConnectionState>>,
    /// Connection attempts counter for reconnection logic.
    connect_attempts: Arc<Mutex<u32>>,
}

impl IpcChannel {
    /// Create a new IPC channel with the given configuration.
    pub fn new(config: IpcConnectionConfig) -> Self {
        Self {
            config,
            stream: Arc::new(Mutex::new(None)),
            state: Arc::new(Mutex::new(ConnectionState::Disconnected)),
            connect_attempts: Arc::new(Mutex::new(0)),
        }
    }
    
    /// Get a reference to the connection configuration.
    pub fn config(&self) -> &IpcConnectionConfig {
        &self.config
    }
    
    /// Connect to the Unix Domain Socket server.
    pub async fn connect(config: IpcConnectionConfig) -> NetworkResult<Self> {
        let channel = Self::new(config);
        channel.connect_with_retry().await?;
        Ok(channel)
    }
    
    /// Connect with retry according to the reconnection policy.
    async fn connect_with_retry(&self) -> NetworkResult<()> {
        // Update state to connecting
        *self.state.lock().await = ConnectionState::Connecting;
        
        // Reset connection attempts counter
        *self.connect_attempts.lock().await = 0;
        
        // Try to connect with the appropriate retry policy
        match &self.config.reconnect_policy {
            ReconnectPolicy::None => {
                // Only try once, with a timeout
                let result = self.try_connect().await;
                if result.is_err() {
                    *self.state.lock().await = ConnectionState::Failed;
                }
                result
            },
            ReconnectPolicy::FixedInterval { delay, max_attempts } => {
                self.connect_fixed_interval(*delay, *max_attempts).await
            },
            ReconnectPolicy::ExponentialBackoff { initial_delay, max_delay, multiplier } => {
                self.connect_exponential_backoff(*initial_delay, *max_delay, *multiplier).await
            }
        }
    }
    
    /// Connect with fixed interval retry policy.
    async fn connect_fixed_interval(
        &self,
        delay: Duration,
        max_attempts: Option<u32>,
    ) -> NetworkResult<()> {
        let mut attempts = 0;
        loop {
            // Check if we've exceeded maximum attempts
            if let Some(max) = max_attempts {
                if attempts >= max {
                    *self.state.lock().await = ConnectionState::Failed;
                    return Err(NetworkError::ReconnectionFailed(
                        attempts,
                        "Maximum reconnection attempts reached".to_string(),
                    ));
                }
            }
            
            // Try to connect
            match self.try_connect().await {
                Ok(()) => return Ok(()),
                Err(e) => {
                    attempts += 1;
                    *self.connect_attempts.lock().await = attempts;
                    
                    warn!(
                        "IPC connection attempt {} failed: {}. Retrying in {:?}",
                        attempts, e, delay
                    );
                    
                    // Wait before next attempt
                    tokio::time::sleep(delay).await;
                }
            }
        }
    }
    
    /// Connect with exponential backoff retry policy.
    async fn connect_exponential_backoff(
        &self,
        initial_delay: Duration,
        max_delay: Duration,
        multiplier: f64,
    ) -> NetworkResult<()> {
        let mut attempts = 0;
        let mut current_delay = initial_delay;
        
        loop {
            // Try to connect
            match self.try_connect().await {
                Ok(()) => return Ok(()),
                Err(e) => {
                    attempts += 1;
                    *self.connect_attempts.lock().await = attempts;
                    
                    warn!(
                        "IPC connection attempt {} failed: {}. Retrying in {:?}",
                        attempts, e, current_delay
                    );
                    
                    // Wait before next attempt
                    tokio::time::sleep(current_delay).await;
                    
                    // Calculate next delay with exponential backoff
                    let next_delay_millis = (current_delay.as_millis() as f64 * multiplier) as u64;
                    current_delay = Duration::from_millis(
                        next_delay_millis.min(max_delay.as_millis() as u64)
                    );
                }
            }
        }
    }
    
    /// Try to connect once with timeout.
    async fn try_connect(&self) -> NetworkResult<()> {
        // Ensure we're not already connected
        if *self.state.lock().await == ConnectionState::Connected {
            return Ok(());
        }
        
        // Update state
        *self.state.lock().await = ConnectionState::Connecting;
        
        // Connect with timeout
        let connect_future = UnixStream::connect(&self.config.socket_path);
        
        // Apply timeout
        let timeout_duration = self.config.timeout;
        let stream = match tokio_timeout(timeout_duration, connect_future).await {
            Ok(Ok(stream)) => stream,
            Ok(Err(e)) => {
                *self.state.lock().await = ConnectionState::Disconnected;
                return Err(NetworkError::ConnectionError(e.to_string()));
            }
            Err(_) => {
                *self.state.lock().await = ConnectionState::Disconnected;
                return Err(NetworkError::ConnectionTimeout(timeout_duration));
            }
        };
        
        // Store the connected stream
        *self.stream.lock().await = Some(stream);
        *self.state.lock().await = ConnectionState::Connected;
        
        info!("Connected to Unix Domain Socket: {}", self.config.socket_path.display());
        Ok(())
    }
    
    /// Send a message over the IPC channel.
    async fn send_message(&self, message: &EncodedMessage) -> NetworkResult<()> {
        // Ensure we're connected
        if *self.state.lock().await != ConnectionState::Connected {
            return Err(NetworkError::ConnectionError(
                "Not connected".to_string(),
            ));
        }
        
        // Lock the stream for writing
        let mut stream_guard = self.stream.lock().await;
        
        if let Some(stream) = &mut *stream_guard {
            // First write the message to a buffer
            let mut buffer = Vec::new();
            message.write_to_async(&mut buffer).await
                .map_err(NetworkError::MessageError)?;
            
            // Write the buffer to the stream
            match stream.write_all(&buffer).await {
                Ok(()) => {
                    // Flush to ensure data is sent
                    match stream.flush().await {
                        Ok(()) => Ok(()),
                        Err(e) => {
                            // Failed to flush, mark as disconnected
                            *self.state.lock().await = ConnectionState::Disconnected;
                            *stream_guard = None;
                            Err(NetworkError::IoError(e))
                        }
                    }
                }
                Err(e) => {
                    // Failed to write, mark as disconnected
                    *self.state.lock().await = ConnectionState::Disconnected;
                    *stream_guard = None;
                    Err(NetworkError::IoError(e))
                }
            }
        } else {
            Err(NetworkError::ConnectionError(
                "Stream is None despite connected state".to_string(),
            ))
        }
    }
    
    /// Receive a message from the IPC channel.
    async fn receive_message(&self) -> NetworkResult<EncodedMessage> {
        // Ensure we're connected
        if *self.state.lock().await != ConnectionState::Connected {
            return Err(NetworkError::ConnectionError(
                "Not connected".to_string(),
            ));
        }
        
        // Lock the stream for reading
        let mut stream_guard = self.stream.lock().await;
        
        if let Some(stream) = &mut *stream_guard {
            // Read the length header (4 bytes)
            let mut len_bytes = [0u8; 4];
            if let Err(e) = stream.read_exact(&mut len_bytes).await {
                // Handle EOF or other errors
                *self.state.lock().await = ConnectionState::Disconnected;
                *stream_guard = None;
                return if e.kind() == std::io::ErrorKind::UnexpectedEof {
                    Err(NetworkError::ConnectionClosed)
                } else {
                    Err(NetworkError::IoError(e))
                };
            }
            let len = u32::from_be_bytes(len_bytes) as usize;
            
            // Read the format byte (1 byte)
            let mut format_byte = [0u8; 1];
            if let Err(e) = stream.read_exact(&mut format_byte).await {
                *self.state.lock().await = ConnectionState::Disconnected;
                *stream_guard = None;
                return if e.kind() == std::io::ErrorKind::UnexpectedEof {
                    Err(NetworkError::ConnectionClosed)
                } else {
                    Err(NetworkError::IoError(e))
                };
            }
            
            // Read the message data
            let mut data = vec![0u8; len];
            if let Err(e) = stream.read_exact(&mut data).await {
                *self.state.lock().await = ConnectionState::Disconnected;
                *stream_guard = None;
                return if e.kind() == std::io::ErrorKind::UnexpectedEof {
                    Err(NetworkError::ConnectionClosed)
                } else {
                    Err(NetworkError::IoError(e))
                };
            }
            
            // Construct the encoded message
            // First recreate the framed message for EncodedMessage::read_from_async
            let mut framed_message_data = Vec::with_capacity(4 + 1 + len);
            framed_message_data.extend_from_slice(&len_bytes);
            framed_message_data.push(format_byte[0]);
            framed_message_data.extend_from_slice(&data);
            
            let mut cursor = std::io::Cursor::new(framed_message_data);
            EncodedMessage::read_from_async(&mut cursor).await
                .map_err(NetworkError::MessageError)
        } else {
            Err(NetworkError::ConnectionError(
                "Stream is None despite connected state".to_string(),
            ))
        }
    }
    
    /// Close the connection.
    async fn close(&self) -> NetworkResult<()> {
        let mut stream_guard = self.stream.lock().await;
        *self.state.lock().await = ConnectionState::Disconnected;
        
        if let Some(stream) = stream_guard.take() {
            // Close the stream gracefully
            drop(stream);
        }
        
        Ok(())
    }
    
    /// Try to reconnect if disconnected.
    async fn ensure_connected(&self) -> NetworkResult<()> {
        // Check current state
        let current_state = *self.state.lock().await;
        
        match current_state {
            ConnectionState::Connected => Ok(()),
            ConnectionState::Failed | ConnectionState::Disconnected | ConnectionState::Connecting => {
                // Reset connection attempts counter for failed connections to allow retry
                if current_state == ConnectionState::Failed {
                    *self.connect_attempts.lock().await = 0;
                }
                
                // Try to reconnect
                self.connect_with_retry().await
            }
        }
    }
    
    /// Send a message with reconnection if needed.
    pub async fn send_with_reconnect(&self, message: EncodedMessage) -> NetworkResult<()> {
        // Try to ensure we're connected first
        self.ensure_connected().await?;
        
        // Try to send the message
        match self.send_message(&message).await {
            Ok(()) => Ok(()),
            Err(e) => {
                // If sending failed due to connection, try to reconnect and retry once
                if matches!(e, 
                    NetworkError::ConnectionError(_) | 
                    NetworkError::ConnectionClosed | 
                    NetworkError::IoError(_)
                ) {
                    // Try to reconnect
                    self.connect_with_retry().await?;
                    
                    // Try sending again after reconnection
                    self.send_message(&message).await
                } else {
                    // Return the original error
                    Err(e)
                }
            }
        }
    }
    
    /// Receive a message with reconnection if needed.
    pub async fn receive_with_reconnect(&self) -> NetworkResult<EncodedMessage> {
        // Try to ensure we're connected first
        self.ensure_connected().await?;
        
        // Try to receive a message
        match self.receive_message().await {
            Ok(message) => Ok(message),
            Err(e) => {
                // If receiving failed due to connection, try to reconnect and retry once
                if matches!(e, 
                    NetworkError::ConnectionError(_) | 
                    NetworkError::ConnectionClosed | 
                    NetworkError::IoError(_)
                ) {
                    // Try to reconnect
                    self.connect_with_retry().await?;
                    
                    // Try receiving again after reconnection
                    self.receive_message().await
                } else {
                    // Return the original error
                    Err(e)
                }
            }
        }
    }
    
    /// Receive a message with timeout.
    pub async fn receive_with_timeout(&self, timeout_duration: Duration) -> NetworkResult<EncodedMessage> {
        match tokio_timeout(timeout_duration, self.receive_with_reconnect()).await {
            Ok(result) => result,
            Err(_) => Err(NetworkError::ConnectionTimeout(timeout_duration)),
        }
    }
}

#[async_trait]
impl MessageChannel for IpcChannel {
    async fn send(&self, message: EncodedMessage) -> MessageResult<()> {
        self.send_with_reconnect(message)
            .await
            .map_err(|e| MessageError::IoError(std::io::Error::other(
                format!("IPC channel error: {}", e),
            )))
    }
    
    async fn receive(&self) -> MessageResult<EncodedMessage> {
        self.receive_with_reconnect()
            .await
            .map_err(|e| MessageError::IoError(std::io::Error::other(
                format!("IPC channel error: {}", e),
            )))
    }
    
    async fn state(&self) -> ConnectionState {
        *self.state.lock().await
    }
    
    async fn connect(&self) -> MessageResult<()> {
        self.connect_with_retry()
            .await
            .map_err(|e| MessageError::IoError(std::io::Error::other(
                format!("IPC channel connection error: {}", e),
            )))
    }
    
    async fn disconnect(&self) -> MessageResult<()> {
        self.close()
            .await
            .map_err(|e| MessageError::IoError(std::io::Error::other(
                format!("IPC channel disconnect error: {}", e),
            )))
    }
}

// Ensure proper cleanup on drop
impl Drop for IpcChannel {
    fn drop(&mut self) {
        // We can't call async functions in drop, so we just log a warning
        debug!("IpcChannel dropped, connection may not be properly closed");
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::message::Message;
    use tokio::fs;
    use tokio::net::UnixListener;
    
    // Test helper to create a mock Unix Domain Socket server
    async fn mock_ipc_server(socket_path: &str) -> NetworkResult<tokio::task::JoinHandle<()>> {
        // Remove the socket file if it exists
        let _ = fs::remove_file(socket_path).await;
        
        let listener = UnixListener::bind(socket_path)?;
        
        let handle = tokio::spawn(async move {
            if let Ok((mut socket, _)) = listener.accept().await {
                // Echo server - read message and echo it back
                loop {
                    // Read the length header (4 bytes)
                    let mut len_bytes = [0u8; 4];
                    if socket.read_exact(&mut len_bytes).await.is_err() {
                        break;
                    }
                    let len = u32::from_be_bytes(len_bytes) as usize;
                    
                    // Read the format byte (1 byte)
                    let mut format_byte = [0u8; 1];
                    if socket.read_exact(&mut format_byte).await.is_err() {
                        break;
                    }
                    
                    // Read the message data
                    let mut data = vec![0u8; len];
                    if socket.read_exact(&mut data).await.is_err() {
                        break;
                    }
                    
                    // Echo back the complete framed message
                    let mut response = Vec::with_capacity(4 + 1 + len);
                    response.extend_from_slice(&len_bytes);
                    response.push(format_byte[0]);
                    response.extend_from_slice(&data);
                    
                    if socket.write_all(&response).await.is_err() {
                        break;
                    }
                }
            }
        });
        
        Ok(handle)
    }
    
    #[tokio::test]
    async fn test_ipc_channel_connect() -> NetworkResult<()> {
        let socket_path = "/tmp/test_ipc_channel_connect.sock";
        let _server_handle = mock_ipc_server(socket_path).await?;
        
        // Give the server a moment to start
        tokio::time::sleep(Duration::from_millis(100)).await;
        
        let config = IpcConnectionConfig::new(socket_path);
        let channel = IpcChannel::connect(config).await?;
        
        assert_eq!(channel.state().await, ConnectionState::Connected);
        
        // Cleanup
        let _ = fs::remove_file(socket_path).await;
        Ok(())
    }
    
    #[tokio::test]
    async fn test_ipc_channel_send_receive() -> NetworkResult<()> {
        let socket_path = "/tmp/test_ipc_channel_send_receive.sock";
        let _server_handle = mock_ipc_server(socket_path).await?;
        
        // Give the server a moment to start
        tokio::time::sleep(Duration::from_millis(100)).await;
        
        let config = IpcConnectionConfig::new(socket_path);
        let channel = IpcChannel::connect(config).await?;
        
        let test_message = Message::new("Hello, IPC World!".to_string());
        let encoded = test_message.encode().unwrap();
        
        // Send message
        channel.send(encoded.clone()).await.unwrap();
        
        // Receive echo
        let received = channel.receive().await.unwrap();
        let decoded: String = received.decode().unwrap();
        
        assert_eq!(decoded, "Hello, IPC World!");
        
        // Cleanup
        let _ = fs::remove_file(socket_path).await;
        Ok(())
    }
    
    #[tokio::test]
    async fn test_ipc_channel_reconnect() -> NetworkResult<()> {
        let socket_path = "/tmp/test_ipc_channel_reconnect.sock";
        
        // Start server
        let server_handle = mock_ipc_server(socket_path).await?;
        tokio::time::sleep(Duration::from_millis(100)).await;
        
        let config = IpcConnectionConfig::new(socket_path)
            .with_reconnect_policy(ReconnectPolicy::FixedInterval {
                delay: Duration::from_millis(100),
                max_attempts: Some(3),
            });
        let channel = IpcChannel::connect(config).await?;
        
        assert_eq!(channel.state().await, ConnectionState::Connected);
        
        // Kill the server
        server_handle.abort();
        tokio::time::sleep(Duration::from_millis(100)).await;
        
        // Attempting to send should eventually disconnect
        let test_message = Message::new("test".to_string());
        let encoded = test_message.encode().unwrap();
        let _ = channel.send(encoded).await; // This should fail and mark as disconnected
        
        // Restart server
        let _new_server_handle = mock_ipc_server(socket_path).await?;
        tokio::time::sleep(Duration::from_millis(100)).await;
        
        // Should be able to reconnect
        let test_message = Message::new("reconnect test".to_string());
        let encoded = test_message.encode().unwrap();
        channel.send(encoded).await.unwrap();
        
        // Cleanup
        let _ = fs::remove_file(socket_path).await;
        Ok(())
    }
} 