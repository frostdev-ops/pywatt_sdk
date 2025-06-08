use crate::communication::ipc_types::Announce as AnnounceBlob;
use std::io::Write;
use thiserror::Error;
use tracing::info;

/// Errors that may occur when serializing or sending announcement
#[derive(Error, Debug)]
pub enum AnnounceError {
    /// Error serializing announcement to JSON
    #[error("Error serializing announcement: {0}")]
    Serialization(#[from] serde_json::Error),

    /// Error writing to stdout
    #[error("Error writing to stdout: {0}")]
    Io(#[from] std::io::Error),
}

/// Send the module's announcement blob to the orchestrator via **stdout**.
///
/// This will write a single-line JSON message and flush stdout.
/// Handles broken pipe errors gracefully to prevent module crashes.
pub fn send_announce(announce: &AnnounceBlob) -> Result<(), AnnounceError> {
    let message_to_orchestrator =
        crate::communication::ipc_types::ModuleToOrchestrator::Announce(announce.clone());
    let json = serde_json::to_string(&message_to_orchestrator)?;
    
    // Try to send announcement, but handle broken pipe gracefully
    match std::io::Write::write_all(&mut std::io::stdout(), json.as_bytes()) {
        Ok(_) => {
            // Try to write newline
            if let Err(e) = std::io::Write::write_all(&mut std::io::stdout(), b"\n") {
                if e.kind() == std::io::ErrorKind::BrokenPipe {
                    tracing::warn!("Broken pipe when writing newline to stdout - orchestrator may have closed connection");
                    return Ok(()); // Don't fail the module for this
                }
                return Err(AnnounceError::Io(e));
            }
            
            // Try to flush
            if let Err(e) = std::io::stdout().flush() {
                if e.kind() == std::io::ErrorKind::BrokenPipe {
                    tracing::warn!("Broken pipe when flushing stdout - orchestrator may have closed connection");
                    return Ok(()); // Don't fail the module for this
                }
                return Err(AnnounceError::Io(e));
            }
            
            info!("Sent announcement to orchestrator");
            Ok(())
        }
        Err(e) => {
            if e.kind() == std::io::ErrorKind::BrokenPipe {
                tracing::warn!("Broken pipe when sending announcement - orchestrator may have closed connection");
                // Log the announcement to stderr for debugging
                tracing::info!("Announcement that failed to send: {}", json);
                Ok(()) // Don't fail the module for this
            } else {
                Err(AnnounceError::Io(e))
            }
        }
    }
} 