#[cfg(feature = "jwt_auth")]
use thiserror::Error;

/// Errors that can occur during JWT authentication.
#[cfg(feature = "jwt_auth")]
#[derive(Error, Debug)]
pub enum JwtAuthError {
    /// The token is missing from the Authorization header.
    #[error("Missing JWT token")]
    MissingToken,

    /// The token signature is invalid.
    #[error("Invalid JWT token signature")]
    InvalidSignature,

    /// The token claims are invalid.
    #[error("Invalid JWT token claims: {0}")]
    InvalidClaims(String),

    /// Error decoding the token.
    #[error("JWT error: {0}")]
    JwtError(#[from] jsonwebtoken::errors::Error),

    /// Error serializing or deserializing token claims.
    #[error("Serialization error: {0}")]
    SerializationError(#[from] serde_json::Error),

    /// Error communicating with the proxy service.
    #[error("Proxy error: {0}")]
    ProxyError(String),
}
