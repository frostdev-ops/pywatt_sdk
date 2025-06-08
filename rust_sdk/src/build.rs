//! Module exposing build information constants and utilities.
//!
//! These values are automatically populated at build time:
//! - `GIT_HASH`: Git commit hash
//! - `BUILD_TIME_UTC`: Build timestamp in RFC3339 format
//! - `RUSTC_VERSION`: Rustc version used to build the crate
//!
//! ## Usage in module build scripts
//!
//! ```rust
//! pywatt_sdk::build::emit_build_info();
//! ```
//!
//! ## Using build info in handlers
//!
//! ```rust
//! use pywatt_sdk::prelude::*;
//! use axum::{Json, response::IntoResponse};
//! use serde_json::json;
//!
//! async fn health_handler() -> impl IntoResponse {
//!     let build_info = get_build_info();
//!     Json(json!({
//!         "status": "healthy",
//!         "build": build_info
//!     }))
//! }
//! ```

/// Git commit hash of the build, or "unknown" if not available.
pub const GIT_HASH: &str = env!("PYWATT_GIT_HASH");

/// Build timestamp in RFC3339 format.
pub const BUILD_TIME_UTC: &str = env!("PYWATT_BUILD_TIME_UTC");

/// Rustc version used for the build.
pub const RUSTC_VERSION: &str = env!("PYWATT_RUSTC_VERSION");

/// Emits build information as cargo environment variables.
///
/// This function should be called from a module's `build.rs` file to emit
/// build metadata that can be accessed at runtime through the constants
/// in this module.
///
/// The following environment variables are emitted:
/// - `PYWATT_GIT_HASH`: Git commit hash (short form)
/// - `PYWATT_BUILD_TIME_UTC`: Build timestamp in RFC3339 format
/// - `PYWATT_RUSTC_VERSION`: Rustc version string
///
/// If git is not available or fails, `GIT_HASH` will be set to "unknown".
/// If rustc version detection fails, `RUSTC_VERSION` will be set to "unknown".
///
/// ## Example
///
/// ```rust
/// pywatt_sdk::build::emit_build_info();
/// ```
///
/// ## Rebuild Triggers
///
/// This function also sets up cargo rebuild triggers:
/// - Changes to `.git/HEAD`
/// - Changes to `.git/refs/heads`
/// - Changes to the build script itself
pub fn emit_build_info() {
    use std::process::Command;
    
    // Get git hash (short form)
    let git_hash = Command::new("git")
        .args(["rev-parse", "--short", "HEAD"])
        .output()
        .map(|output| {
            if output.status.success() {
                String::from_utf8_lossy(&output.stdout).trim().to_string()
            } else {
                "unknown".to_string()
            }
        })
        .unwrap_or_else(|_| "unknown".to_string());

    // Get current build timestamp
    let build_time = chrono::Utc::now().to_rfc3339();

    // Get rustc version
    let rustc_version = Command::new("rustc")
        .arg("--version")
        .output()
        .map(|output| {
            if output.status.success() {
                String::from_utf8_lossy(&output.stdout).trim().to_string()
            } else {
                "unknown".to_string()
            }
        })
        .unwrap_or_else(|_| "unknown".to_string());

    // Emit environment variables for cargo
    println!("cargo:rustc-env=PYWATT_GIT_HASH={}", git_hash);
    println!("cargo:rustc-env=PYWATT_BUILD_TIME_UTC={}", build_time);
    println!("cargo:rustc-env=PYWATT_RUSTC_VERSION={}", rustc_version);

    // Set up rebuild triggers
    println!("cargo:rerun-if-changed=.git/HEAD");
    println!("cargo:rerun-if-changed=.git/refs/heads");
    println!("cargo:rerun-if-changed=.git/index");
    println!("cargo:rerun-if-changed=build.rs");
    
    // Output build information for debugging
    println!("cargo:warning=Build info: git={}, time={}, rustc={}", 
             git_hash, build_time, rustc_version);
}

/// Returns build information as a structured object.
///
/// This is useful for including build information in health check endpoints
/// or module status responses.
///
/// ## Example
///
/// ```rust
/// use pywatt_sdk::build;
/// 
/// let info = build::get_build_info();
/// println!("Module built from commit: {}", info.git_hash);
/// ```
#[derive(Debug, Clone, serde::Serialize)]
pub struct BuildInfo {
    /// Git commit hash (short form)
    pub git_hash: &'static str,
    /// Build timestamp in RFC3339 format
    pub build_time_utc: &'static str,
    /// Rustc version used for the build
    pub rustc_version: &'static str,
}

impl BuildInfo {
    /// Creates a new BuildInfo with current constants.
    pub fn new() -> Self {
        Self {
            git_hash: GIT_HASH,
            build_time_utc: BUILD_TIME_UTC,
            rustc_version: RUSTC_VERSION,
        }
    }
}

impl Default for BuildInfo {
    fn default() -> Self {
        Self::new()
    }
}

/// Convenience function to get build information as a structured object.
///
/// Returns a `BuildInfo` struct containing the git hash, build timestamp,
/// and rustc version information for the current module.
pub fn get_build_info() -> BuildInfo {
    BuildInfo::new()
}
