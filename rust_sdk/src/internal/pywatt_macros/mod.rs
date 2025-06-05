//! PyWatt SDK Procedural Macro Integration Module
//!
//! This module conditionally re-exports the core `module` procedural macro when the
//! `proc_macros` feature is enabled. Actual macro implementations reside in a separate
//! `pywatt_macros` proc-macro crate (with `crate-type = "proc-macro"`).
//!
//! # Usage
//!
//! ```rust
//! #[cfg(feature = "proc_macros")]
//! pub use crate::internal::macros::module;
//! ```
//!
//! To enable, add to your `Cargo.toml`:
//!
//! ```toml
//! [features]
//! proc_macros = []
//! ```

#[cfg(feature = "proc_macros")]
pub use crate::internal::macros::module;