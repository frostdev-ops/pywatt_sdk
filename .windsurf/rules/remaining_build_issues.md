---
trigger: model_decision
description: 
globs: 
---
# Remaining Build Issues

<context>
This rule documents the remaining build issues in the PyWatt-Rust project and how to fix them.
</context>

<issues>

## Decimal vs BigDecimal Conversion

The project is using rust_decimal::Decimal in model structs but SQLx's BigDecimal is returned from queries. To fix this:

1. Change model structs to use sqlx::types::BigDecimal instead of rust_decimal::Decimal
2. Implement proper conversion traits between the types
3. Use `::numeric` casting in SQL queries with BigDecimal fields
4. When passing Decimal values to queries, convert them to BigDecimal first

## Transaction Handling

When using transactions, use `&mut *tx` instead of `&*tx` to satisfy the Executor trait:

```rust
// Incorrect:
.execute(&*tx)

// Correct:
.execute(&mut *tx)
```

## OpenID Connect Client Configuration

The OIDC client creation has endpoint type mismatches:

1. Ensure the return type of `create_oidc_client` matches the expected type
2. Use proper client creation methods based on discovery
3. Fix method name issues (use `user_info` instead of `userinfo`)
4. Ensure proper closure syntax for state and nonce parameters

## API Key Auth Extractor Lifetimes

The API key auth extractor needs proper lifetimes:

```rust
// Correct implementation
#[async_trait]
impl<S> FromRequestParts<S> for ApiKeyAuth
where
    S: AsRef<AppState> + Send + Sync,
{
    type Rejection = AppError;

    async fn from_request_parts<'a, 's>(
        parts: &'a mut Parts, 
        state: &'s S,
    ) -> Result<Self, Self::Rejection> {
        // Implementation...
    }
}
```

</issues>

<next_steps>

## Priority Order for Fixes

1. Fix transaction handling first as it's simpler
2. Fix OIDC client configuration issues
3. Fix numeric type issues (most widespread)

## Decimal Handling Strategy

Options for fixing Decimal vs BigDecimal mismatches:

1. Update model structs to use sqlx::types::BigDecimal consistently
2. Implement conversions in the service layer
3. Use numeric casting (::numeric) in all SQL queries
4. Ensure Cargo.toml has the sqlx "bigdecimal" feature enabled

## OAuth/OIDC Strategy

For fixing OAuth/OIDC issues:

1. Separate OIDC vs OAuth2 clients more clearly
2. Use proper endpoint discovery and configuration
3. Fix method naming inconsistencies (user_info vs userinfo)
4. Use proper closures for state and nonce

</next_steps>

<patterns>

## Fixed Patterns

### Proper Float Casting in SQL
```rust
// For f64 fields
sqlx::query_as!(
    Estimate,
    r#"
    SELECT id, customer_id, number, amount::float8, currency,
    status as "status: EstimateStatus", valid_until, accepted_at, rejected_at,
    created_at, updated_at, metadata, description, line_items, terms, notes
    FROM estimates
    WHERE id = $1
    "#,
    id
)
```

### Proper Transaction Usage
```rust
// Start a transaction
let mut tx = pool.begin().await?;

// Execute the first query
sqlx::query!(
    "INSERT INTO items (id, name) VALUES ($1, $2)",
    item_id,
    name
)
.execute(&mut *tx)
.await?;

// Execute another query in the same transaction
sqlx::query!(
    "UPDATE counters SET value = value + 1"
)
.execute(&mut *tx)
.await?;

// Commit the transaction
tx.commit().await?;
```

### Proper Axum Extractor Implementation
```rust
#[async_trait]
impl<S> FromRequestParts<S> for MyExtractor
where
    S: Send + Sync,
{
    type Rejection = AppError;

    async fn from_request_parts<'a, 's>(
        parts: &'a mut Parts,
        state: &'s S,
    ) -> Result<Self, Self::Rejection> {
        // Implementation...
        Ok(Self {})
    }
}
```

</patterns>

<testing>

## Validating Fixes

After making changes, test with the following:

1. `cargo check` to verify compilation
2. `cargo clippy` to catch additional issues
3. Run unit tests for affected modules
4. Test API endpoints with numeric data
5. Test OAuth/OIDC flows with mock providers

</testing>
