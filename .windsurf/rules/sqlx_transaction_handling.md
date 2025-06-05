---
trigger: model_decision
description: This rule documents proper transaction handling patterns for SQLx in the PyWatt-Rust project, focusing on executor references, error handling, and commit/rollback patterns.
globs: 
---
# SQLx Transaction Handling

<context>
This rule documents proper transaction handling patterns for SQLx in the PyWatt-Rust project, focusing on executor references, error handling, and commit/rollback patterns.
</context>

<rules>

## Executor Reference Rules
- When executing queries within a transaction, always use `&mut *tx` pattern to get a mutable reference
- Never use `&*tx` as SQLx's `execute()` method requires a mutable reference
- For pool references, use `&*pool` or `&mut *pool` depending on the operation

## Transaction Flow
- Begin transactions with `pool.begin().await?`
- Always explicitly commit with `tx.commit().await?` or rollback with `tx.rollback().await?`
- Use `?` operator to propagate SQLx errors within a transaction
- Handle transaction errors properly to ensure rollback on failure

## Error Handling
- Wrap transactions in a block with proper error handling
- If custom error handling is needed, ensure the transaction is rolled back
- Consider using a helper function for common transaction patterns
- Document potential transaction errors in function comments

## Performance Considerations
- Keep transactions as short as possible to avoid database contention
- Avoid unnecessary queries within a transaction
- Consider using read-only transactions for queries that don't modify data
- For long-running operations, consider breaking them into smaller transactions

</rules>

<patterns>

## Proper Transaction Pattern
```rust
// Begin a transaction
let mut tx = pool.begin().await?;

// Execute queries within the transaction using &mut *tx
sqlx::query!("INSERT INTO items (id, name) VALUES ($1, $2)", id, name)
    .execute(&mut *tx)
    .await?;

sqlx::query!("UPDATE counters SET value = value + 1 WHERE name = 'items'")
    .execute(&mut *tx)
    .await?;

// Commit the transaction
tx.commit().await?;
```

## Transaction with Error Handling
```rust
// Begin a transaction
let mut tx = pool.begin().await?;

// Try to execute queries, handling errors
let result: AppResult<()> = async {
    sqlx::query!("INSERT INTO items (id, name) VALUES ($1, $2)", id, name)
        .execute(&mut *tx)
        .await?;

    sqlx::query!("UPDATE counters SET value = value + 1 WHERE name = 'items'")
        .execute(&mut *tx)
        .await?;

    Ok(())
}.await;

// Handle the result
match result {
    Ok(_) => {
        tx.commit().await?;
        Ok(())
    }
    Err(e) => {
        let _ = tx.rollback().await; // Ignore rollback errors
        Err(e)
    }
}
```

## Transaction Helper Function
```rust
/// Execute multiple queries in a transaction
pub async fn with_transaction<F, R>(pool: &PgPool, f: F) -> AppResult<R>
where
    F: for<'c> FnOnce(&'c mut Transaction<'_, Postgres>) -> BoxFuture<'c, AppResult<R>>,
    R: Send + 'static,
{
    let mut tx = pool.begin().await?;
    
    match f(&mut tx).await {
        Ok(result) => {
            tx.commit().await?;
            Ok(result)
        }
        Err(error) => {
            let _ = tx.rollback().await;
            Err(error)
        }
    }
}
```

</patterns>

<examples>

## Service Method with Transaction
```rust
/// Create a new user with associated preferences
pub async fn create_user_with_preferences(
    &self,
    user_data: CreateUserDto,
    preferences: UserPreferencesDto,
) -> AppResult<User> {
    // Begin a transaction
    let mut tx = self.db_pool.begin().await?;
    
    // Create the user first
    let user = sqlx::query_as!(
        User,
        r#"
        INSERT INTO users (name, email, password_hash, created_at)
        VALUES ($1, $2, $3, NOW())
        RETURNING id, name, email, created_at, updated_at
        "#,
        user_data.name,
        user_data.email,
        user_data.password_hash
    )
    .fetch_one(&mut *tx)
    .await?;
    
    // Then create user preferences
    sqlx::query!(
        r#"
        INSERT INTO user_preferences (user_id, theme, language, notifications_enabled)
        VALUES ($1, $2, $3, $4)
        "#,
        user.id,
        preferences.theme,
        preferences.language,
        preferences.notifications_enabled
    )
    .execute(&mut *tx)
    .await?;
    
    // Commit the transaction
    tx.commit().await?;
    
    Ok(user)
}
```

## Read-Only Transaction
```rust
/// Get a user with all their associated data in a single read-only transaction
pub async fn get_user_with_data(&self, user_id: Uuid) -> AppResult<UserWithData> {
    // Begin a transaction as read-only if supported by your database
    let mut tx = self.db_pool.begin().await?;
    
    // Get the user
    let user = sqlx::query_as!(
        User,
        r#"SELECT * FROM users WHERE id = $1"#,
        user_id
    )
    .fetch_optional(&mut *tx)
    .await?
    .ok_or_else(|| AppError::NotFound(format!("User not found: {}", user_id)))?;
    
    // Get user preferences
    let preferences = sqlx::query_as!(
        UserPreferences,
        r#"SELECT * FROM user_preferences WHERE user_id = $1"#,
        user_id
    )
    .fetch_one(&mut *tx)
    .await?;
    
    // Get user roles
    let roles = sqlx::query_as!(
        Role,
        r#"
        SELECT r.* FROM roles r
        JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = $1
        "#,
        user_id
    )
    .fetch_all(&mut *tx)
    .await?;
    
    // Commit or rollback (not strictly necessary for read-only)
    tx.commit().await?;
    
    Ok(UserWithData {
        user,
        preferences,
        roles,
    })
}
```

</examples>

<troubleshooting>

## Common Errors
- "the trait bound `&PgConnection: sqlx::Executor<'_>` is not satisfied"
  - Cause: Using `&*tx` instead of `&mut *tx`
  - Fix: Change to `&mut *tx` to provide a mutable reference

- "cannot move out of `tx` which is behind a mutable reference"
  - Cause: Trying to move a transaction after using a reference to it
  - Fix: Make sure you don't use the transaction after committing or rolling back

- "error[E0599]: no method named `rollback` found for struct `Transaction<'_, Postgres>`"
  - Cause: Using a transaction after it's been committed or rolled back
  - Fix: Don't use a transaction after a terminal operation

## Debugging Tips
- Check PostgreSQL logs for transaction errors and deadlocks
- Ensure you're not holding transactions open for too long
- Make sure all paths either commit or rollback the transaction
- For complex transactions, consider adding debug logs before/after key operations

</troubleshooting>
