---
trigger: always_on
description: 
globs: 
---
# Rust Code Style Guide

<context>
This style guide defines the coding standards and formatting rules for the PyWatt-Rust project. It ensures consistency and maintainability across the codebase.
</context>

<rules>

## File Organization
- One module per file
- Place tests in a `tests` submodule at the bottom of the file
- Group imports by standard library, external crates, and local modules
- Place `use` statements at the top of the file, after the module doc comment

## Module Structure
- Start with module-level documentation (`//!`)
- Follow with imports
- Then type definitions
- Then trait implementations
- Finally, function implementations
- Place private items after public ones

## Formatting
- Use 4 spaces for indentation
- Maximum line length of 100 characters
- No trailing whitespace
- End files with a newline
- Use spaces around operators
- No spaces inside brackets

## Comments
- Use `///` for public API documentation
- Use `//` for implementation comments
- Write complete sentences with proper punctuation
- Keep comments up to date with code changes
- Document non-obvious code behavior

## Naming
- Use descriptive, clear names
- Avoid abbreviations except for common ones (e.g., `id`, `http`)
- Use verb phrases for functions (`get_user`, `create_post`)
- Use noun phrases for types (`UserProfile`, `PostContent`)
- Use `is_` or `has_` prefix for boolean methods

</rules>

<patterns>

## Function Declarations
```rust
pub fn function_name(
    arg1: Type1,
    arg2: Type2,
) -> ReturnType {
    // Implementation
}
```

## Trait Implementations
```rust
impl TraitName for StructName {
    fn method_name(
        &self,
        arg: ArgType,
    ) -> ReturnType {
        // Implementation
    }
}
```

## Error Handling
```rust
fn fallible_operation() -> Result<Success, Error> {
    let value = something_that_might_fail()?;
    Ok(value)
}
```

## Generic Constraints
```rust
fn generic_function<T, E>(value: T) -> Result<T, E>
where
    T: Display + Clone,
    E: Error,
{
    // Implementation
}
```

</patterns>

<examples>

## Module Organization
```rust
//! Module documentation here.

use std::{fmt, io};
use external_crate::{Type1, Type2};
use crate::local_module::LocalType;
// Public types first
pub struct PublicStruct {
    field: Type1,
}

// Then public traits
pub trait PublicTrait {
    fn method(&self) -> Result<(), Error>;
}

// Then public functions
pub fn public_function() -> Result<(), Error> {
    // Implementation
}

// Then private items
struct PrivateStruct {
    field: Type2,
}

// Tests at the bottom
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_something() {
        // Test implementation
    }
}
```

## Error Type Definition
```rust
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("not found: {0}")]
    NotFound(String),
    
    #[error("invalid input: {0}")]
    InvalidInput(String),
    
    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),
}
```

## Configuration Struct
```rust
#[derive(Debug, serde::Deserialize)]
pub struct Config {
    #[serde(default = "default_port")]
    pub port: u16,
    
    pub database_url: String,
    
    #[serde(with = "humantime_serde")]
    pub timeout: Duration,
}
```

</examples>

<lints>

## Required Lints
```rust
#![warn(
    clippy::all,
    clippy::pedantic,
    clippy::nursery,
    rust_2018_idioms
)]
```

## Allowed Lints
```rust
#![allow(
    clippy::module_name_repetitions,
    clippy::similar_names
)]
```

</lints>

<tooling>

## Required Tools
- rustfmt (for code formatting)
- clippy (for linting)
- cargo-audit (for security audits)
- cargo-edit (for dependency management)

## Editor Configuration
- Enable format on save
- Enable clippy on save
- Set tab width to 4 spaces
- Set max line length to 100

</tooling>
