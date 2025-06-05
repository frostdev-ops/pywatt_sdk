---
trigger: model_decision
description: This rule documents the necessity and usage of the `chrono` feature flag for the `sqlx` crate in the PyWatt-Rust project, particularly for handling `TIMESTAMPTZ` database types.
globs: 
---
# Cursor Rule: sqlx_chrono_feature

<context>
This rule documents the necessity and usage of the `chrono` feature flag for the `sqlx` crate in the PyWatt-Rust project, particularly for handling `TIMESTAMPTZ` database types.
</context>

<rules>

## Problem: Time Type Mismatch

By default, `sqlx` maps PostgreSQL `TIMESTAMP`/`TIMESTAMPTZ` types to Rust's `time::OffsetDateTime` type. However, the PyWatt-Rust codebase predominantly uses `chrono::DateTime<Utc>` for timestamp representation, often leveraging its `serde` integration.

Attempting to use `sqlx::query_as!` to map a `TIMESTAMPTZ` column directly to a `chrono::DateTime<Utc>` field without enabling the correct feature will result in compilation errors related to missing `sqlx::Type` or `sqlx::Decode` implementations for `chrono::DateTime<Utc>`.

## Solution: Enable `chrono` Feature

To enable direct mapping between `TIMESTAMPTZ` and `chrono::DateTime<Utc>`, the `chrono` feature must be enabled for the `sqlx` dependency in the relevant `Cargo.toml` file.

```toml
# Example: finance_service/Cargo.toml

[dependencies]
# ... other dependencies
sqlx = { version = "0.8.5", features = [
    "postgres", 
    "runtime-tokio-native-tls", # or other runtime
    "macros", 
    "chrono", # <--- Enable this feature
    "uuid"    # <--- Also enable uuid if using Uuid type
]}
chrono = { version = "0.4", features = ["serde"] }
# ...
```

## Usage in Code

Once the `chrono` feature is enabled:

1.  **Model Structs**: Define timestamp fields using `chrono::DateTime<Utc>`.

    ```rust
    use chrono::{DateTime, Utc};
    use uuid::Uuid;
    use sqlx::FromRow;
    
    #[derive(Debug, Clone, FromRow)]
    pub struct Client {
        pub id: Uuid,
        // ... other fields
        pub created_at: DateTime<Utc>,
        pub updated_at: DateTime<Utc>,
    }
    ```

2.  **SQLx Queries**: Use `sqlx::query_as!` or map rows manually. `sqlx` will now correctly decode `TIMESTAMPTZ` columns into `DateTime<Utc>` fields.

    ```rust
    use chrono::{DateTime, Utc};
    // ...
    
    async fn get_client(pool: &PgPool, id: Uuid) -> Result<Option<Client>, sqlx::Error> {
        let client_opt = sqlx::query_as!(
            Client,
            r#"
            SELECT 
                id, name, email, -- ... other fields ...
                created_at, -- Mapped to DateTime<Utc>
                updated_at  -- Mapped to DateTime<Utc>
            FROM clients
            WHERE id = $1
            "#,
            id
        )
        .fetch_optional(pool)
        .await?;
        Ok(client_opt)
    }
    ```

3.  **Binding Timestamps**: When inserting or updating, bind `chrono::DateTime<Utc>` values directly.

    ```rust
     use chrono::{DateTime, Utc};
     // ...
     
    async fn create_client(pool: &PgPool, /* ... */) -> Result<Client, sqlx::Error> {
        let now = Utc::now();
        let client = sqlx::query_as!(
            Client,
            r#"
            INSERT INTO clients (/* columns */, created_at, updated_at)
            VALUES (/* $1, $2, ... */, $N, $N+1)
            RETURNING id, name, /* ... */, created_at, updated_at
            "#,
            // ... other bind values ...
            now, // Bind DateTime<Utc> for created_at
            now  // Bind DateTime<Utc> for updated_at
        )
        .fetch_one(pool)
        .await?;
        Ok(client)
    }
    ```

## Required Features

Ensure the following features are consistently enabled for `sqlx` across the workspace where needed:

-   `postgres`: For PostgreSQL database interaction.
-   A runtime feature (e.g., `runtime-tokio-native-tls`, `runtime-tokio-rustls`).
-   `macros`: For `query!`, `query_as!`, etc.
-   `chrono`: For `chrono::DateTime<Utc>` support.
-   `uuid`: For `uuid::Uuid` support.

</rules>
