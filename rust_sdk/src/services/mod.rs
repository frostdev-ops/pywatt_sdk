//! High-level SDK features: registration, announcements, model management, embedded server.

pub mod registration;
pub mod announce;
pub mod model_manager;
pub mod server;
// Re-export router_discovery for direct imports from services
pub use announce::router_discovery; 