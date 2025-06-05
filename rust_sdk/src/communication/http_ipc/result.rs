//! HTTP result types and error handling for the HTTP IPC module.
//!
//! This module provides standardized error types and response helper functions
//! for HTTP over IPC communication, with improved error handling and detailed
//! diagnostics.

use crate::ipc_types::IpcHttpResponse;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use thiserror::Error;
use tracing::{debug, error, trace};

/// HTTP IPC specific errors
#[derive(Debug, Error)]
pub enum HttpIpcError {
    #[error("Invalid request: {0}")]
    InvalidRequest(String),

    #[error("Not found: {0}")]
    NotFound(String),

    #[error("Unauthorized: {0}")]
    Unauthorized(String),

    #[error("Forbidden: {0}")]
    Forbidden(String),

    #[error("Internal error: {0}")]
    Internal(String),

    #[error("SDK error: {0}")]
    Sdk(#[from] crate::Error),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("Timeout: {0}")]
    Timeout(String),
    
    #[error("IPC communication error: {0}")]
    IpcCommunication(String),

    #[error("Other error: {0}")]
    Other(String),
}

impl From<std::io::Error> for HttpIpcError {
    fn from(err: std::io::Error) -> Self {
        Self::Internal(format!("IO error: {}", err))
    }
}

impl From<tokio::time::error::Elapsed> for HttpIpcError {
    fn from(err: tokio::time::error::Elapsed) -> Self {
        Self::Timeout(format!("Operation timed out: {}", err))
    }
}

/// Result type for HTTP IPC operations
pub type HttpResult<T> = std::result::Result<T, HttpIpcError>;

/// Parse JSON request body with detailed error reporting
pub fn parse_json_body<T: for<'de> Deserialize<'de>>(body: &Option<Vec<u8>>, request_id: &str) -> HttpResult<T> {
    match body {
        Some(data) => {
            trace!("Parsing JSON body (request_id: {}, size: {} bytes)", request_id, data.len());
            
            // For small bodies, log the content at trace level for debugging
            if data.len() < 1024 {
                if let Ok(json_str) = std::str::from_utf8(data) {
                    trace!("Raw JSON body (request_id: {}): {}", request_id, json_str);
                }
            }
            
            match serde_json::from_slice(data) {
                Ok(parsed) => {
                    debug!("Successfully parsed JSON body (request_id: {})", request_id);
                    Ok(parsed)
                },
                Err(e) => {
                    error!("Failed to parse JSON body (request_id: {}): {}", request_id, e);
                    
                    // Attempt to get more context about the parse error
                    let error_details = if let Ok(partial_json) = std::str::from_utf8(data) {
                        let truncated = if partial_json.len() > 100 {
                            format!("{}...", &partial_json[..100])
                        } else {
                            partial_json.to_string()
                        };
                        format!("Error: {}, JSON: {}", e, truncated)
                    } else {
                        format!("Error: {}, non-UTF8 data", e)
                    };
                    
                    Err(HttpIpcError::InvalidRequest(format!("Invalid JSON body: {}", error_details)))
                }
            }
        },
        None => {
            error!("Missing request body (request_id: {})", request_id);
            Err(HttpIpcError::InvalidRequest(
                "Request body is required".to_string(),
            ))
        }
    }
}

/// Create a JSON response with detailed logging
pub fn json_response<T: Serialize>(
    data: T, 
    status_code: u16,
    request_id: &str
) -> HttpResult<IpcHttpResponse> {
    debug!("Creating JSON response (request_id: {}, status_code: {})", request_id, status_code);
    
    let response = super::ApiResponse {
        status: "success".to_string(),
        data: Some(data),
        message: None,
    };

    // Serialize the response to JSON
    let body = match serde_json::to_vec(&response) {
        Ok(body) => {
            trace!("Serialized JSON response (request_id: {}, size: {} bytes)", request_id, body.len());
            body
        },
        Err(e) => {
            error!("Failed to serialize JSON response (request_id: {}): {}", request_id, e);
            return Err(HttpIpcError::Json(e));
        }
    };

    // Create headers with content type
    let mut headers = HashMap::new();
    headers.insert("Content-Type".to_string(), "application/json".to_string());
    
    // Add correlation headers for request tracing
    headers.insert("X-Request-ID".to_string(), request_id.to_string());

    Ok(IpcHttpResponse {
        request_id: request_id.to_string(),
        status_code,
        headers,
        body: Some(body),
    })
}

/// Create a success response
pub fn success<T: Serialize>(data: T, request_id: &str) -> HttpResult<IpcHttpResponse> {
    json_response(data, 200, request_id)
}

/// Create a created response (201)
pub fn created<T: Serialize>(data: T, request_id: &str) -> HttpResult<IpcHttpResponse> {
    json_response(data, 201, request_id)
}

/// Create an accepted response (202)
pub fn accepted<T: Serialize>(data: T, request_id: &str) -> HttpResult<IpcHttpResponse> {
    json_response(data, 202, request_id)
}

/// Create an error response with detailed diagnostics
pub fn error_response<T: Serialize>(
    message: &str,
    status_code: u16,
    request_id: &str,
    error_code: Option<&str>,
) -> HttpResult<IpcHttpResponse> {
    debug!("Creating error response (request_id: {}, status_code: {}, message: {})",
           request_id, status_code, message);
    
    // Extended response structure for errors
    let response = super::ApiResponse::<T> {
        status: "error".to_string(),
        data: None,
        message: Some(message.to_string()),
    };

    // Serialize the response to JSON
    let body = match serde_json::to_vec(&response) {
        Ok(body) => body,
        Err(e) => {
            error!("Failed to serialize error response (request_id: {}): {}", request_id, e);
            return Err(HttpIpcError::Json(e));
        }
    };

    // Create headers with content type
    let mut headers = HashMap::new();
    headers.insert("Content-Type".to_string(), "application/json".to_string());
    headers.insert("X-Request-ID".to_string(), request_id.to_string());
    
    // Add error code if provided
    if let Some(code) = error_code {
        headers.insert("X-Error-Code".to_string(), code.to_string());
    }

    Ok(IpcHttpResponse {
        request_id: request_id.to_string(),
        status_code,
        headers,
        body: Some(body),
    })
}

/// Create a bad request response (400)
pub fn bad_request(message: &str, request_id: &str) -> HttpResult<IpcHttpResponse> {
    error_response::<()>(message, 400, request_id, Some("BAD_REQUEST"))
}

/// Create an unauthorized response (401)
pub fn unauthorized(message: &str, request_id: &str) -> HttpResult<IpcHttpResponse> {
    error_response::<()>(message, 401, request_id, Some("UNAUTHORIZED"))
}

/// Create a forbidden response (403)
pub fn forbidden(message: &str, request_id: &str) -> HttpResult<IpcHttpResponse> {
    error_response::<()>(message, 403, request_id, Some("FORBIDDEN"))
}

/// Create a not found response (404)
pub fn not_found(path: &str, request_id: &str) -> HttpResult<IpcHttpResponse> {
    error_response::<()>(&format!("Endpoint not found: {}", path), 404, request_id, Some("NOT_FOUND"))
}

/// Create a method not allowed response (405)
pub fn method_not_allowed(method: &str, path: &str, request_id: &str) -> HttpResult<IpcHttpResponse> {
    error_response::<()>(
        &format!("Method {} not allowed for endpoint {}", method, path),
        405,
        request_id,
        Some("METHOD_NOT_ALLOWED")
    )
}

/// Create a conflict response (409)
pub fn conflict(message: &str, request_id: &str) -> HttpResult<IpcHttpResponse> {
    error_response::<()>(message, 409, request_id, Some("CONFLICT"))
}

/// Create a timeout response (408)
pub fn timeout(message: &str, request_id: &str) -> HttpResult<IpcHttpResponse> {
    error_response::<()>(message, 408, request_id, Some("TIMEOUT"))
}

/// Create an internal server error response (500)
pub fn internal_error(message: &str, request_id: &str) -> HttpResult<IpcHttpResponse> {
    error_response::<()>(message, 500, request_id, Some("INTERNAL_ERROR"))
}

/// Convert an error to an HTTP response with detailed diagnostics
pub(crate) fn error_to_response(error: HttpIpcError, request_id: &str) -> IpcHttpResponse {
    let (status_code, error_code) = match &error {
        HttpIpcError::InvalidRequest(_) => (400, "BAD_REQUEST"),
        HttpIpcError::NotFound(_) => (404, "NOT_FOUND"),
        HttpIpcError::Unauthorized(_) => (401, "UNAUTHORIZED"),
        HttpIpcError::Forbidden(_) => (403, "FORBIDDEN"),
        HttpIpcError::Timeout(_) => (408, "TIMEOUT"),
        HttpIpcError::IpcCommunication(_) => (502, "IPC_COMMUNICATION_ERROR"),
        _ => (500, "INTERNAL_ERROR"),
    };

    error!("Converting error to HTTP response (request_id: {}, status: {}, error: {})",
           request_id, status_code, error);

    let response = super::ApiResponse::<()> {
        status: "error".to_string(),
        data: None,
        message: Some(error.to_string()),
    };

    // Create headers with content type
    let mut headers = HashMap::new();
    headers.insert("Content-Type".to_string(), "application/json".to_string());
    headers.insert("X-Request-ID".to_string(), request_id.to_string());
    headers.insert("X-Error-Code".to_string(), error_code.to_string());

    // Attempt to serialize the response, fallback to plain text if that fails
    match serde_json::to_vec(&response) {
        Ok(body) => IpcHttpResponse {
            request_id: request_id.to_string(),
            status_code,
            headers,
            body: Some(body),
        },
        Err(e) => {
            error!("Failed to serialize error response (request_id: {}): {}", request_id, e);
            headers.insert("Content-Type".to_string(), "text/plain".to_string());
            IpcHttpResponse {
                request_id: request_id.to_string(),
                status_code,
                headers,
                body: Some(format!("Error: {}", error).into_bytes()),
            }
        }
    }
}

/// Helper to create a diagnostic response for debugging IPC communication issues
pub fn diagnostic_response(request_id: &str) -> IpcHttpResponse {
    let timestamp = chrono::Utc::now().to_rfc3339();
    let message = format!("IPC diagnostic response generated at {}", timestamp);
    
    debug!("Creating diagnostic response (request_id: {})", request_id);
    
    let response = super::ApiResponse::<()> {
        status: "diagnostic".to_string(),
        data: None,
        message: Some(message.clone()),
    };
    
    let mut headers = HashMap::new();
    headers.insert("Content-Type".to_string(), "application/json".to_string());
    headers.insert("X-Request-ID".to_string(), request_id.to_string());
    headers.insert("X-Response-Type".to_string(), "diagnostic".to_string());
    
    match serde_json::to_vec(&response) {
        Ok(body) => IpcHttpResponse {
            request_id: request_id.to_string(),
            status_code: 200,
            headers,
            body: Some(body),
        },
        Err(_) => {
            headers.insert("Content-Type".to_string(), "text/plain".to_string());
            IpcHttpResponse {
                request_id: request_id.to_string(),
                status_code: 200,
                headers,
                body: Some(message.into_bytes()),
            }
        }
    }
}
