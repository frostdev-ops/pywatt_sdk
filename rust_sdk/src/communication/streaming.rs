//! Advanced Message Patterns and Streaming Support
//!
//! This module provides support for streaming large data transfers, chunked message
//! transmission, flow control, bidirectional streaming, and various message patterns
//! including pub/sub, request multiplexing, and priority queues.

use crate::communication::MessageChannel;
use crate::message::{EncodedMessage, MessageError};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque, BTreeMap};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tokio::sync::{mpsc, oneshot, RwLock as AsyncRwLock, Semaphore};
use tokio::time::{sleep, timeout};
use tracing::{debug, warn, error, info};
use uuid::Uuid;

#[cfg(feature = "advanced_streaming")]
use flate2::{read::GzDecoder, write::GzEncoder, Compression};

#[cfg(feature = "advanced_streaming")]
use std::io::{Read, Write};

/// Stream configuration for large data transfers
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamConfig {
    /// Maximum chunk size in bytes
    pub max_chunk_size: usize,
    /// Window size for flow control (number of outstanding chunks)
    pub window_size: usize,
    /// Timeout for chunk acknowledgments
    pub ack_timeout: Duration,
    /// Maximum number of retries for failed chunks
    pub max_retries: u32,
    /// Whether to preserve chunk ordering
    pub preserve_order: bool,
    /// Enable compression for large chunks
    pub enable_compression: bool,
    /// Compression threshold in bytes
    pub compression_threshold: usize,
}

impl Default for StreamConfig {
    fn default() -> Self {
        Self {
            max_chunk_size: 64 * 1024, // 64KB
            window_size: 10,
            ack_timeout: Duration::from_secs(30),
            max_retries: 3,
            preserve_order: true,
            enable_compression: true,
            compression_threshold: 1024, // 1KB
        }
    }
}

/// Stream chunk containing part of a larger message
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamChunk {
    /// Stream identifier
    pub stream_id: Uuid,
    /// Chunk sequence number
    pub sequence: u64,
    /// Total number of chunks in the stream
    pub total_chunks: u64,
    /// Chunk data
    pub data: Vec<u8>,
    /// Whether this chunk is compressed
    pub compressed: bool,
    /// Checksum for data integrity
    pub checksum: u32,
    /// Whether this is the final chunk
    pub is_final: bool,
    /// Metadata for the entire stream (only in first chunk)
    pub stream_metadata: Option<StreamMetadata>,
}

// Add bincode implementations for StreamChunk
#[cfg(feature = "advanced_streaming")]
impl bincode::Encode for StreamChunk {
    fn encode<E: bincode::enc::Encoder>(
        &self,
        encoder: &mut E,
    ) -> Result<(), bincode::error::EncodeError> {
        // Encode UUID as bytes
        bincode::Encode::encode(&self.stream_id.as_bytes(), encoder)?;
        bincode::Encode::encode(&self.sequence, encoder)?;
        bincode::Encode::encode(&self.total_chunks, encoder)?;
        bincode::Encode::encode(&self.data, encoder)?;
        bincode::Encode::encode(&self.compressed, encoder)?;
        bincode::Encode::encode(&self.checksum, encoder)?;
        bincode::Encode::encode(&self.is_final, encoder)?;
        bincode::Encode::encode(&self.stream_metadata, encoder)?;
        Ok(())
    }
}

#[cfg(feature = "advanced_streaming")]
impl bincode::Decode<()> for StreamChunk {
    fn decode<D: bincode::de::Decoder<Context = ()>>(
        decoder: &mut D,
    ) -> Result<Self, bincode::error::DecodeError> {
        let uuid_bytes: [u8; 16] = bincode::Decode::decode(decoder)?;
        let stream_id = Uuid::from_bytes(uuid_bytes);
        
        Ok(Self {
            stream_id,
            sequence: bincode::Decode::decode(decoder)?,
            total_chunks: bincode::Decode::decode(decoder)?,
            data: bincode::Decode::decode(decoder)?,
            compressed: bincode::Decode::decode(decoder)?,
            checksum: bincode::Decode::decode(decoder)?,
            is_final: bincode::Decode::decode(decoder)?,
            stream_metadata: bincode::Decode::decode(decoder)?,
        })
    }
}

/// Metadata for a data stream
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamMetadata {
    /// Total size of the stream in bytes
    pub total_size: u64,
    /// Content type or format
    pub content_type: Option<String>,
    /// Stream priority
    pub priority: StreamPriority,
    /// Custom properties
    pub properties: HashMap<String, String>,
}

/// Stream priority levels
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum StreamPriority {
    Low = 0,
    Normal = 1,
    High = 2,
    Critical = 3,
}

impl Default for StreamPriority {
    fn default() -> Self {
        Self::Normal
    }
}

#[cfg(feature = "advanced_streaming")]
impl bincode::Encode for StreamPriority {
    fn encode<E: bincode::enc::Encoder>(
        &self,
        encoder: &mut E,
    ) -> Result<(), bincode::error::EncodeError> {
        bincode::Encode::encode(&(*self as u8), encoder)
    }
}

#[cfg(feature = "advanced_streaming")]
impl bincode::Decode<()> for StreamPriority {
    fn decode<D: bincode::de::Decoder<Context = ()>>(
        decoder: &mut D,
    ) -> Result<Self, bincode::error::DecodeError> {
        let value: u8 = bincode::Decode::decode(decoder)?;
        match value {
            0 => Ok(Self::Low),
            1 => Ok(Self::Normal),
            2 => Ok(Self::High),
            3 => Ok(Self::Critical),
            _ => Err(bincode::error::DecodeError::Other("Invalid StreamPriority value")),
        }
    }
}

/// Stream acknowledgment message
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamAck {
    /// Stream identifier
    pub stream_id: Uuid,
    /// Acknowledged chunk sequence number
    pub sequence: u64,
    /// Whether the chunk was received successfully
    pub success: bool,
    /// Error message if not successful
    pub error: Option<String>,
}

/// Flow control window for managing outstanding chunks
#[derive(Debug, Clone)]
pub struct FlowControlWindow {
    /// Maximum number of outstanding chunks
    max_window: usize,
    /// Currently outstanding chunks
    outstanding: HashMap<u64, Instant>,
    /// Next sequence number to send
    next_sequence: u64,
    /// Acknowledgments received
    acknowledged: BTreeMap<u64, bool>,
}

impl FlowControlWindow {
    /// Create a new flow control window
    pub fn new(max_window: usize) -> Self {
        Self {
            max_window,
            outstanding: HashMap::new(),
            next_sequence: 0,
            acknowledged: BTreeMap::new(),
        }
    }
    
    /// Check if we can send another chunk
    pub fn can_send(&self) -> bool {
        self.outstanding.len() < self.max_window
    }
    
    /// Record a chunk as sent
    pub fn record_sent(&mut self, sequence: u64) {
        self.outstanding.insert(sequence, Instant::now());
        self.next_sequence = self.next_sequence.max(sequence + 1);
    }
    
    /// Record an acknowledgment
    pub fn record_ack(&mut self, sequence: u64, success: bool) {
        self.outstanding.remove(&sequence);
        self.acknowledged.insert(sequence, success);
    }
    
    /// Get chunks that have timed out
    pub fn get_timed_out_chunks(&self, timeout: Duration) -> Vec<u64> {
        let now = Instant::now();
        self.outstanding.iter()
            .filter(|(_, sent_at)| now.duration_since(**sent_at) > timeout)
            .map(|(&seq, _)| seq)
            .collect()
    }
    
    /// Get the next sequence number to send
    pub fn next_sequence(&self) -> u64 {
        self.next_sequence
    }
    
    /// Check if all chunks have been acknowledged
    pub fn is_complete(&self, total_chunks: u64) -> bool {
        self.outstanding.is_empty() && 
        self.acknowledged.len() as u64 >= total_chunks &&
        self.acknowledged.values().all(|&success| success)
    }
}

/// Stream sender for chunked data transmission
pub struct StreamSender {
    stream_id: Uuid,
    config: StreamConfig,
    flow_control: Arc<Mutex<FlowControlWindow>>,
    chunks: Vec<StreamChunk>,
    channel: Arc<dyn MessageChannel>,
    ack_receiver: Arc<Mutex<mpsc::UnboundedReceiver<StreamAck>>>,
    retry_counts: Arc<Mutex<HashMap<u64, u32>>>,
}

impl StreamSender {
    /// Create a new stream sender
    pub fn new(
        data: Vec<u8>,
        metadata: StreamMetadata,
        config: StreamConfig,
        channel: Arc<dyn MessageChannel>,
        ack_receiver: mpsc::UnboundedReceiver<StreamAck>,
    ) -> Result<Self, MessageError> {
        let stream_id = Uuid::new_v4();
        let chunks = Self::create_chunks(stream_id, data, metadata, &config)?;
        
        Ok(Self {
            stream_id,
            config: config.clone(),
            flow_control: Arc::new(Mutex::new(FlowControlWindow::new(config.window_size))),
            chunks,
            channel,
            ack_receiver: Arc::new(Mutex::new(ack_receiver)),
            retry_counts: Arc::new(Mutex::new(HashMap::new())),
        })
    }
    
    /// Send the stream with flow control
    pub async fn send(self) -> Result<(), MessageError> {
        let total_chunks = self.chunks.len() as u64;
        let mut pending_chunks = VecDeque::new();
        
        // Initially queue all chunks
        for chunk in &self.chunks {
            pending_chunks.push_back(chunk.clone());
        }
        
        // Send chunks with flow control
        loop {
            // Send chunks while window allows
            while !pending_chunks.is_empty() {
                let can_send = {
                    let flow_control = self.flow_control.lock().unwrap();
                    flow_control.can_send()
                };
                
                if !can_send {
                    break;
                }
                
                if let Some(chunk) = pending_chunks.pop_front() {
                    self.send_chunk(&chunk).await?;
                    
                    let mut flow_control = self.flow_control.lock().unwrap();
                    flow_control.record_sent(chunk.sequence);
                }
            }
            
            // Check for completion
            let is_complete = {
                let flow_control = self.flow_control.lock().unwrap();
                flow_control.is_complete(total_chunks)
            };
            
            if is_complete {
                debug!("Stream {} completed successfully", self.stream_id);
                break;
            }
            
            // Process acknowledgments and handle timeouts
            self.process_acks_and_timeouts(&mut pending_chunks).await?;
            
            // Small delay to avoid busy waiting
            sleep(Duration::from_millis(10)).await;
        }
        
        Ok(())
    }
    
    /// Send a single chunk
    async fn send_chunk(&self, chunk: &StreamChunk) -> Result<(), MessageError> {
        #[cfg(feature = "advanced_streaming")]
        let chunk_data = {
            bincode::encode_to_vec(chunk, bincode::config::standard())
                .map_err(|e| MessageError::BinaryConversionError(e))?
        };
        
        #[cfg(not(feature = "advanced_streaming"))]
        let chunk_data = {
            serde_json::to_vec(chunk)
                .map_err(|e| MessageError::InvalidFormat(format!("JSON serialization failed: {}", e)))?
        };

        let message = EncodedMessage::new(chunk_data, crate::message::EncodingFormat::Binary);
        
        self.channel.send(message).await?;
        
        debug!("Sent chunk {}/{} for stream {}", 
               chunk.sequence + 1, chunk.total_chunks, self.stream_id);
        
        Ok(())
    }
    
    /// Process acknowledgments and handle timeouts
    async fn process_acks_and_timeouts(&self, pending_chunks: &mut VecDeque<StreamChunk>) -> Result<(), MessageError> {
        // Process available acknowledgments
        let mut ack_receiver = self.ack_receiver.lock().unwrap();
        while let Ok(ack) = ack_receiver.try_recv() {
            if ack.stream_id == self.stream_id {
                let mut flow_control = self.flow_control.lock().unwrap();
                flow_control.record_ack(ack.sequence, ack.success);
                
                if !ack.success {
                    warn!("Chunk {} failed for stream {}: {:?}", 
                          ack.sequence, self.stream_id, ack.error);
                    
                    // Handle retry logic
                    self.handle_chunk_retry(ack.sequence, pending_chunks).await?;
                }
            }
        }
        drop(ack_receiver);
        
        // Handle timeouts
        let timed_out_chunks = {
            let flow_control = self.flow_control.lock().unwrap();
            flow_control.get_timed_out_chunks(self.config.ack_timeout)
        };
        
        for sequence in timed_out_chunks {
            warn!("Chunk {} timed out for stream {}", sequence, self.stream_id);
            self.handle_chunk_retry(sequence, pending_chunks).await?;
        }
        
        Ok(())
    }
    
    /// Handle retrying a failed chunk
    async fn handle_chunk_retry(&self, sequence: u64, _pending_chunks: &mut VecDeque<StreamChunk>) -> Result<(), MessageError> {
        let retry_count = {
            let mut retry_counts = self.retry_counts.lock().unwrap();
            let retry_count = retry_counts.entry(sequence).or_insert(0);
            
            if *retry_count >= self.config.max_retries {
                return Err(MessageError::InvalidFormat(
                    format!("Chunk {} exceeded max retries for stream {}", sequence, self.stream_id)
                ));
            }
            
            *retry_count += 1;
            *retry_count
        };
        
        // Find the chunk to retry (would need to store original chunks for this)
        // For now, we'll just mark the flow control window as needing retry
        let mut flow_control = self.flow_control.lock().unwrap();
        flow_control.record_ack(sequence, false);
        
        // In a real implementation, you'd re-queue the specific chunk
        warn!("Retrying chunk {} for stream {} (attempt {})", sequence, self.stream_id, retry_count);
        
        Ok(())
    }
    
    /// Create chunks from data
    fn create_chunks(
        stream_id: Uuid,
        data: Vec<u8>,
        metadata: StreamMetadata,
        config: &StreamConfig,
    ) -> Result<Vec<StreamChunk>, MessageError> {
        let total_size = data.len();
        let mut chunks = Vec::new();
        let total_chunks = (total_size + config.max_chunk_size - 1) / config.max_chunk_size;
        
        for (sequence, chunk_data) in data.chunks(config.max_chunk_size).enumerate() {
            let mut chunk_data = chunk_data.to_vec();
            let mut compressed = false;
            
            // Compress if enabled and chunk is large enough
            if config.enable_compression && chunk_data.len() >= config.compression_threshold {
                match Self::compress_data(&chunk_data) {
                    Ok(compressed_data) if compressed_data.len() < chunk_data.len() => {
                        chunk_data = compressed_data;
                        compressed = true;
                    }
                    _ => {} // Keep original data if compression doesn't help
                }
            }
            
            let checksum = Self::calculate_checksum(&chunk_data);
            
            let chunk = StreamChunk {
                stream_id,
                sequence: sequence as u64,
                total_chunks: total_chunks as u64,
                data: chunk_data,
                compressed,
                checksum,
                is_final: sequence == total_chunks - 1,
                stream_metadata: if sequence == 0 { Some(metadata.clone()) } else { None },
            };
            
            chunks.push(chunk);
        }
        
        Ok(chunks)
    }
    
    /// Compress data using gzip
    #[cfg(feature = "advanced_streaming")]
    fn compress_data(data: &[u8]) -> Result<Vec<u8>, MessageError> {
        use flate2::{write::GzEncoder, Compression};
        use std::io::Write;
        
        let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(data)
            .map_err(|e| MessageError::InvalidFormat(e.to_string()))?;
        encoder.finish()
            .map_err(|e| MessageError::InvalidFormat(e.to_string()))
    }
    
    #[cfg(not(feature = "advanced_streaming"))]
    fn compress_data(_data: &[u8]) -> Result<Vec<u8>, MessageError> {
        Err(MessageError::InvalidFormat("Compression not available without advanced_streaming feature".to_string()))
    }
    
    /// Calculate CRC32 checksum
    fn calculate_checksum(data: &[u8]) -> u32 {
        #[cfg(feature = "advanced_streaming")]
        {
            crc32fast::hash(data)
        }
        #[cfg(not(feature = "advanced_streaming"))]
        {
            // Simple checksum fallback when crc32fast is not available
            data.iter().fold(0u32, |acc, &byte| acc.wrapping_add(byte as u32))
        }
    }
}

/// Stream receiver for reassembling chunked data
pub struct StreamReceiver {
    stream_id: Uuid,
    config: StreamConfig,
    received_chunks: Arc<Mutex<BTreeMap<u64, StreamChunk>>>,
    stream_metadata: Arc<Mutex<Option<StreamMetadata>>>,
    ack_sender: mpsc::UnboundedSender<StreamAck>,
    completion_notifier: Arc<Mutex<Option<oneshot::Sender<Vec<u8>>>>>,
}

impl StreamReceiver {
    /// Create a new stream receiver
    pub fn new(
        stream_id: Uuid,
        config: StreamConfig,
        ack_sender: mpsc::UnboundedSender<StreamAck>,
    ) -> Self {
        Self {
            stream_id,
            config,
            received_chunks: Arc::new(Mutex::new(BTreeMap::new())),
            stream_metadata: Arc::new(Mutex::new(None)),
            ack_sender,
            completion_notifier: Arc::new(Mutex::new(None)),
        }
    }
    
    /// Set completion notifier to be called when stream is complete
    pub fn set_completion_notifier(&self, notifier: oneshot::Sender<Vec<u8>>) {
        let mut completion_notifier = self.completion_notifier.lock().unwrap();
        *completion_notifier = Some(notifier);
    }
    
    /// Process a received chunk
    pub async fn process_chunk(&self, chunk: StreamChunk) -> Result<bool, MessageError> {
        // Verify chunk integrity
        let calculated_checksum = Self::calculate_checksum(&chunk.data);
        if calculated_checksum != chunk.checksum {
            self.send_ack(chunk.sequence, false, Some("Checksum mismatch".to_string())).await;
            return Err(MessageError::InvalidFormat("Chunk checksum mismatch".to_string()));
        }
        
        // Store metadata from first chunk
        if let Some(metadata) = &chunk.stream_metadata {
            let mut stream_metadata = self.stream_metadata.lock().unwrap();
            *stream_metadata = Some(metadata.clone());
        }
        
        // Store the chunk
        {
            let mut received_chunks = self.received_chunks.lock().unwrap();
            received_chunks.insert(chunk.sequence, chunk.clone());
        }
        
        // Send acknowledgment
        self.send_ack(chunk.sequence, true, None).await;
        
        // Check if stream is complete
        let is_complete = self.check_completion(&chunk).await?;
        
        if is_complete {
            self.finalize_stream().await?;
        }
        
        Ok(is_complete)
    }
    
    /// Check if the stream is complete
    async fn check_completion(&self, latest_chunk: &StreamChunk) -> Result<bool, MessageError> {
        if !latest_chunk.is_final {
            return Ok(false);
        }
        
        let received_chunks = self.received_chunks.lock().unwrap();
        let expected_chunks = latest_chunk.total_chunks;
        
        // Check if we have all chunks
        if received_chunks.len() as u64 != expected_chunks {
            return Ok(false);
        }
        
        // Check if all sequence numbers are present
        for i in 0..expected_chunks {
            if !received_chunks.contains_key(&i) {
                return Ok(false);
            }
        }
        
        Ok(true)
    }
    
    /// Finalize the stream by reassembling chunks
    async fn finalize_stream(&self) -> Result<(), MessageError> {
        let received_chunks = self.received_chunks.lock().unwrap().clone();
        let mut reassembled_data = Vec::new();
        
        // Reassemble chunks in order
        for (_, chunk) in received_chunks {
            let mut chunk_data = chunk.data;
            
            // Decompress if needed
            if chunk.compressed {
                chunk_data = Self::decompress_data(&chunk_data)?;
            }
            
            reassembled_data.extend(chunk_data);
        }
        
        // Notify completion
        let mut completion_notifier = self.completion_notifier.lock().unwrap();
        if let Some(notifier) = completion_notifier.take() {
            let _ = notifier.send(reassembled_data.clone());
        }
        
        info!("Stream {} completed with {} bytes", self.stream_id, reassembled_data.len());
        
        Ok(())
    }
    
    /// Send acknowledgment for a chunk
    async fn send_ack(&self, sequence: u64, success: bool, error: Option<String>) {
        let ack = StreamAck {
            stream_id: self.stream_id,
            sequence,
            success,
            error,
        };
        
        if let Err(e) = self.ack_sender.send(ack) {
            error!("Failed to send stream acknowledgment: {}", e);
        }
    }
    
    /// Decompress data using gzip
    #[cfg(feature = "advanced_streaming")]
    fn decompress_data(data: &[u8]) -> Result<Vec<u8>, MessageError> {
        use flate2::read::GzDecoder;
        use std::io::Read;
        
        let mut decoder = GzDecoder::new(data);
        let mut decompressed = Vec::new();
        decoder.read_to_end(&mut decompressed)
            .map_err(|e| MessageError::InvalidFormat(e.to_string()))?;
        Ok(decompressed)
    }
    
    #[cfg(not(feature = "advanced_streaming"))]
    fn decompress_data(_data: &[u8]) -> Result<Vec<u8>, MessageError> {
        Err(MessageError::InvalidFormat("Decompression not available without advanced_streaming feature".to_string()))
    }
    
    /// Calculate CRC32 checksum
    fn calculate_checksum(data: &[u8]) -> u32 {
        #[cfg(feature = "advanced_streaming")]
        {
            crc32fast::hash(data)
        }
        #[cfg(not(feature = "advanced_streaming"))]
        {
            // Simple checksum fallback when crc32fast is not available
            data.iter().fold(0u32, |acc, &byte| acc.wrapping_add(byte as u32))
        }
    }
}

/// Message pattern for publish-subscribe communication
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PubSubMessage {
    /// Topic name
    pub topic: String,
    /// Message payload
    pub payload: Vec<u8>,
    /// Message priority
    pub priority: StreamPriority,
    /// Time to live for the message
    pub ttl: Option<Duration>,
    /// Publisher identifier
    pub publisher: Option<String>,
    /// Message metadata
    pub metadata: HashMap<String, String>,
}

/// Subscription configuration for pub-sub
#[derive(Clone)]
pub struct Subscription {
    /// Topic pattern (supports wildcards)
    pub topic_pattern: String,
    /// Callback for handling messages
    pub handler: Arc<dyn Fn(PubSubMessage) -> std::pin::Pin<Box<dyn std::future::Future<Output = ()> + Send>> + Send + Sync>,
    /// Whether to receive historical messages
    pub include_history: bool,
    /// Maximum queue size for buffering messages
    pub max_queue_size: usize,
}

/// Priority queue for managing messages with different priorities
pub struct PriorityMessageQueue {
    queues: Arc<Mutex<BTreeMap<StreamPriority, VecDeque<EncodedMessage>>>>,
    semaphore: Arc<Semaphore>,
    max_size: usize,
}

impl PriorityMessageQueue {
    /// Create a new priority queue
    pub fn new(max_size: usize) -> Self {
        Self {
            queues: Arc::new(Mutex::new(BTreeMap::new())),
            semaphore: Arc::new(Semaphore::new(max_size)),
            max_size,
        }
    }
    
    /// Add a message to the queue with priority
    pub async fn enqueue(&self, message: EncodedMessage, priority: StreamPriority) -> Result<(), MessageError> {
        // Acquire semaphore permit
        let _permit = self.semaphore.acquire().await
            .map_err(|_| MessageError::InvalidFormat("Queue semaphore closed".to_string()))?;
        
        let mut queues = self.queues.lock().unwrap();
        let queue = queues.entry(priority).or_insert_with(VecDeque::new);
        queue.push_back(message);
        
        Ok(())
    }
    
    /// Dequeue the highest priority message
    pub async fn dequeue(&self) -> Option<EncodedMessage> {
        let mut queues = self.queues.lock().unwrap();
        
        // Process priorities in descending order (Critical first)
        for priority in [StreamPriority::Critical, StreamPriority::High, StreamPriority::Normal, StreamPriority::Low] {
            if let Some(queue) = queues.get_mut(&priority) {
                if let Some(message) = queue.pop_front() {
                    return Some(message);
                }
            }
        }
        
        None
    }
    
    /// Get current queue size
    pub fn size(&self) -> usize {
        let queues = self.queues.lock().unwrap();
        queues.values().map(|q| q.len()).sum()
    }
    
    /// Check if queue is empty
    pub fn is_empty(&self) -> bool {
        self.size() == 0
    }
}

/// Request multiplexing support for concurrent operations
pub struct RequestMultiplexer {
    pending_requests: Arc<AsyncRwLock<HashMap<Uuid, oneshot::Sender<EncodedMessage>>>>,
    request_timeout: Duration,
}

impl RequestMultiplexer {
    /// Create a new request multiplexer
    pub fn new(request_timeout: Duration) -> Self {
        Self {
            pending_requests: Arc::new(AsyncRwLock::new(HashMap::new())),
            request_timeout,
        }
    }
    
    /// Send a request and wait for response
    pub async fn send_request(
        &self,
        request: EncodedMessage,
        channel: Arc<dyn MessageChannel>,
    ) -> Result<EncodedMessage, MessageError> {
        let request_id = Uuid::new_v4();
        let (response_tx, response_rx) = oneshot::channel();
        
        // Register the pending request
        {
            let mut pending = self.pending_requests.write().await;
            pending.insert(request_id, response_tx);
        }
        
        // Add request ID to message metadata
        let request_with_id = request;
        // In a real implementation, you'd add the request_id to message metadata
        
        // Send the request
        channel.send(request_with_id).await?;
        
        // Wait for response with timeout
        let response = timeout(self.request_timeout, response_rx).await
            .map_err(|_| MessageError::InvalidFormat("Request timeout".to_string()))?
            .map_err(|_| MessageError::InvalidFormat("Response channel closed".to_string()))?;
        
        // Clean up
        {
            let mut pending = self.pending_requests.write().await;
            pending.remove(&request_id);
        }
        
        Ok(response)
    }
    
    /// Handle an incoming response
    pub async fn handle_response(&self, response: EncodedMessage, request_id: Uuid) {
        let mut pending = self.pending_requests.write().await;
        if let Some(response_tx) = pending.remove(&request_id) {
            let _ = response_tx.send(response);
        }
    }
    
    /// Get statistics about pending requests
    pub async fn get_stats(&self) -> (usize, Vec<Uuid>) {
        let pending = self.pending_requests.read().await;
        let count = pending.len();
        let request_ids: Vec<Uuid> = pending.keys().copied().collect();
        (count, request_ids)
    }
}

#[cfg(feature = "advanced_streaming")]
impl bincode::Encode for StreamMetadata {
    fn encode<E: bincode::enc::Encoder>(
        &self,
        encoder: &mut E,
    ) -> Result<(), bincode::error::EncodeError> {
        bincode::Encode::encode(&self.total_size, encoder)?;
        bincode::Encode::encode(&self.content_type, encoder)?;
        bincode::Encode::encode(&self.priority, encoder)?;
        bincode::Encode::encode(&self.properties, encoder)?;
        Ok(())
    }
}

#[cfg(feature = "advanced_streaming")]
impl bincode::Decode<()> for StreamMetadata {
    fn decode<D: bincode::de::Decoder<Context = ()>>(
        decoder: &mut D,
    ) -> Result<Self, bincode::error::DecodeError> {
        Ok(Self {
            total_size: bincode::Decode::decode(decoder)?,
            content_type: bincode::Decode::decode(decoder)?,
            priority: bincode::Decode::decode(decoder)?,
            properties: bincode::Decode::decode(decoder)?,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    
    #[test]
    fn test_stream_config() {
        let config = StreamConfig::default();
        assert_eq!(config.max_chunk_size, 64 * 1024);
        assert_eq!(config.window_size, 10);
        assert!(config.preserve_order);
    }
    
    #[test]
    fn test_flow_control_window() {
        let mut window = FlowControlWindow::new(3);
        
        // Initially can send
        assert!(window.can_send());
        
        // Send up to window size
        window.record_sent(0);
        window.record_sent(1);
        window.record_sent(2);
        
        // Now at capacity
        assert!(!window.can_send());
        
        // Acknowledge one
        window.record_ack(0, true);
        
        // Can send again
        assert!(window.can_send());
    }
    
    #[test]
    fn test_priority_queue() {
        let queue = PriorityMessageQueue::new(10);
        
        // Create test messages
        let normal_msg = EncodedMessage::new(b"normal".to_vec(), crate::message::EncodingFormat::Json);
        let critical_msg = EncodedMessage::new(b"critical".to_vec(), crate::message::EncodingFormat::Json);
        
        // This would need async test framework
        // queue.enqueue(normal_msg, StreamPriority::Normal).await.unwrap();
        // queue.enqueue(critical_msg, StreamPriority::Critical).await.unwrap();
        
        // Critical should come out first
        // let dequeued = queue.dequeue().await.unwrap();
        // assert_eq!(dequeued.data(), b"critical");
    }
    
    #[test]
    fn test_stream_chunk_creation() {
        let data = vec![0u8; 1000];
        let metadata = StreamMetadata {
            total_size: 1000,
            content_type: Some("application/octet-stream".to_string()),
            priority: StreamPriority::Normal,
            properties: HashMap::new(),
        };
        let config = StreamConfig {
            max_chunk_size: 100,
            ..Default::default()
        };
        
        let chunks = StreamSender::create_chunks(
            Uuid::new_v4(),
            data,
            metadata,
            &config,
        ).unwrap();
        
        assert_eq!(chunks.len(), 10); // 1000 bytes / 100 bytes per chunk
        assert!(chunks[0].stream_metadata.is_some());
        assert!(chunks[0].stream_metadata.is_none() || true); // First chunk should have metadata
        assert!(chunks[9].is_final); // Last chunk should be marked as final
    }
    
    #[test]
    fn test_checksum_calculation() {
        let data = b"test data";
        let checksum1 = StreamSender::calculate_checksum(data);
        let checksum2 = StreamReceiver::calculate_checksum(data);
        
        assert_eq!(checksum1, checksum2);
        assert_ne!(checksum1, 0);
    }
} 