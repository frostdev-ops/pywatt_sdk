#![allow(clippy::empty_line_after_doc_comments)]
/// Module providing macro functionality for PyWatt SDK.
///
/// This module provides basic macro support for PyWatt modules.
/// Full proc-macro functionality is available in the separate `pywatt_macros` crate.

/// Basic module setup functionality.
/// 
/// This function provides the core module initialization that would
/// typically be wrapped by the `#[pywatt::module]` macro.
/// 
/// When proc_macros feature is disabled, users should call this
/// function manually at the start of their module's main function.
/// 
/// # Usage
/// 
/// ```ignore
/// async fn main() -> Result<(), Box<dyn std::error::Error>> {
///     pywatt_sdk::module_init().await?;
///     // Your module code here
///     Ok(())
/// }
/// ```
pub async fn module_init() -> Result<(), crate::Error> {
    // Initialize the PyWatt module environment
    crate::core::logging::init_module();
    Ok(())
}

/// Re-export for compatibility when proc_macros feature is enabled.
#[cfg(feature = "proc_macros")]
pub use ::pywatt_macros::module;

/// Placeholder module function when proc_macros feature is disabled.
/// 
/// When the proc_macros feature is not enabled, this provides a
/// compile-time placeholder. Users should manually call `module_init()`
/// or use the functions from the main SDK instead.
#[cfg(not(feature = "proc_macros"))]
pub fn module() {
    // No-op when feature is disabled - users should manually initialize
    // This is just a placeholder for compilation when proc_macros are not available
}
