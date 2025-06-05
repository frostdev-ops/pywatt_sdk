---
trigger: model_decision
description: This rule documents best practices for working with SQLx transactions in the PyWatt-Rust project, focusing on proper transaction management, error handling, and mutable references.
globs: 
---
# SQLx Transaction Best Practices

<context>
This rule documents best practices for working with SQLx transactions in the PyWatt-Rust project, focusing on proper transaction management, error handling, and mutable references.
</context>

<rules>

## Transaction Creation and Usage
- Always use `pool.begin().await?` to start a transaction
- Store transactions in a mutable variable: `let mut tx = pool.begin().await?`
- Use `&mut *tx` when passing the transaction to query execution methods
- Explicitly commit or roll back transactions with `tx.commit().await?` or `tx.rollback().await?`
- Never allow transactions to drop without being committed or rolled back
- Use a separate transaction for logically separate operations

## Error Handling
- Use the `?` operator to propagate errors within a transaction
- Always roll back transactions on error conditions
- Consider using a helper function or macro for common transaction patterns
- In complex flows, implement custom rollback logic on error
- Document transaction error handling in function comments

## Performance Considerations
- Keep transactions as short as possible
- Avoid blocking operations inside transactions
- Consider using savepoints for complex operations
- Measure transaction performance in high-load scenarios
- Monitor transaction isolation levels for performance impact

## Code Organization
- Extract complex transaction logic into separate functions
- Keep transaction management code separate from business logic when possible
- Use clear variable names for transactions (tx, transaction, etc.)
- Consider using transaction manager patterns for complex applications
- Document transaction boundaries and lifecycle in comments

</rules>

<patterns>

## Basic Transaction Pattern
```rust
pub async fn create_with_relations(
    &self,
    item: &NewItem,
    relation_ids: &[Uuid],
) -> AppResult<Item> {
    // Start a transaction
    let mut tx = self.pool.begin().await?;
    
    // First operation
    let item = sqlx::query_as!(
        Item,
        r#"
        INSERT INTO items (name, description)
        VALUES ($1, $2)
        RETURNING id, name, description, created_at, updated_at
        "#,
        item.name,
        item.description
    )
    .fetch_one(&mut *tx)
    .await?;
    
    // Second operation within the same transaction
    for relation_id in relation_ids {
        sqlx::query!(
            r#"
            INSERT INTO item_relations (item_id, relation_id)
            VALUES ($1, $2)
            "#,
            item.id,
            relation_id
        )
        .execute(&mut *tx)
        .await?;
    }
    
    // Commit the transaction
    tx.commit().await?;
    
    Ok(item)
}
```

## Error Handling with Rollback
```rust
pub async fn transfer_funds(
    &self,
    from_account_id: Uuid,
    to_account_id: Uuid,
    amount: Decimal,
) -> AppResult<()> {
    // Start a transaction
    let mut tx = self.pool.begin().await?;
    
    // Check if source account has sufficient funds
    let source_balance = sqlx::query_scalar!(
        r#"
        SELECT balance::numeric FROM accounts
        WHERE id = $1
        FOR UPDATE
        "#,
        from_account_id
    )
    .fetch_one(&mut *tx)
    .await?;
    
    if source_balance < amount {
        // Explicitly roll back on error condition
        tx.rollback().await?;
        return Err(AppError::InsufficientFunds);
    }
    
    // Deduct from source account
    sqlx::query!(
        r#"
        UPDATE accounts 
        SET balance = balance - $1, updated_at = NOW()
        WHERE id = $2
        "#,
        amount,
        from_account_id
    )
    .execute(&mut *tx)
    .await?;
    
    // Add to destination account
    sqlx::query!(
        r#"
        UPDATE accounts 
        SET balance = balance + $1, updated_at = NOW()
        WHERE id = $2
        "#,
        amount,
        to_account_id
    )
    .execute(&mut *tx)
    .await?;
    
    // Record the transaction
    sqlx::query!(
        r#"
        INSERT INTO account_transactions 
        (from_account_id, to_account_id, amount, transaction_type)
        VALUES ($1, $2, $3, 'transfer')
        "#,
        from_account_id,
        to_account_id,
        amount
    )
    .execute(&mut *tx)
    .await?;
    
    // Commit the transaction
    tx.commit().await?;
    
    Ok(())
}
```

## Using Savepoints
```rust
pub async fn bulk_operation(
    &self,
    operations: &[Operation],
) -> AppResult<BulkResult> {
    // Start a transaction
    let mut tx = self.pool.begin().await?;
    let mut successful = Vec::new();
    let mut failed = Vec::new();
    
    for (index, operation) in operations.iter().enumerate() {
        // Create a savepoint for each operation
        let savepoint = format!("op_{}", index);
        sqlx::query(&format!("SAVEPOINT {}", savepoint))
            .execute(&mut *tx)
            .await?;
        
        // Try to perform the operation
        let result = self.perform_operation(operation, &mut tx).await;
        
        match result {
            Ok(result) => {
                successful.push(result);
                // Let the savepoint go (implicitly released)
            }
            Err(e) => {
                // Roll back to the savepoint on error
                sqlx::query(&format!("ROLLBACK TO SAVEPOINT {}", savepoint))
                    .execute(&mut *tx)
                    .await?;
                
                failed.push((operation.id, e));
            }
        }
    }
    
    // Commit the transaction with successful operations
    tx.commit().await?;
    
    Ok(BulkResult {
        successful,
        failed,
    })
}
```

</patterns>

<examples>

## Complete User Registration Transaction
```rust
pub async fn register_user(
    &self,
    username: &str,
    email: &str,
    password: &str,
) -> AppResult<User> {
    // Start a transaction
    let mut tx = self.pool.begin().await?;
    
    // Check if username or email already exists
    let existing = sqlx::query!(
        r#"
        SELECT id FROM users WHERE username = $1 OR email = $2
        "#,
        username,
        email
    )
    .fetch_optional(&mut *tx)
    .await?;
    
    if existing.is_some() {
        tx.rollback().await?;
        return Err(AppError::UserAlreadyExists);
    }
    
    // Hash password
    let password_hash = self.password_service.hash_password(password).await?;
    
    // Create user
    let user = sqlx::query_as!(
        User,
        r#"
        INSERT INTO users (username, email, password_hash, role)
        VALUES ($1, $2, $3, 'user')
        RETURNING id, username, email, role as "role: UserRole", created_at, updated_at
        "#,
        username,
        email,
        password_hash
    )
    .fetch_one(&mut *tx)
    .await?;
    
    // Create default profile
    sqlx::query!(
        r#"
        INSERT INTO user_profiles (user_id, display_name)
        VALUES ($1, $2)
        "#,
        user.id,
        username
    )
    .execute(&mut *tx)
    .await?;
    
    // Create email verification token
    let token = Uuid::new_v4().to_string();
    sqlx::query!(
        r#"
        INSERT INTO verification_tokens (user_id, token_type, token, expires_at)
        VALUES ($1, 'email_verification', $2, $3)
        "#,
        user.id,
        token,
        Utc::now() + Duration::days(7)
    )
    .execute(&mut *tx)
    .await?;
    
    // Commit all changes
    tx.commit().await?;
    
    // Queue verification email (outside transaction)
    self.email_service.queue_verification_email(user.id, email, &token).await?;
    
    Ok(user)
}
```

## Transaction in a Service Method
```rust
pub async fn convert_invoice_to_paid(
    &self,
    invoice_id: Uuid,
    payment_method: &str,
    transaction_id: &str,
) -> AppResult<Invoice> {
    // Start a transaction
    let mut tx = self.pool.begin().await?;
    
    // Get the invoice and lock it
    let invoice = sqlx::query_as!(
        Invoice,
        r#"
        SELECT 
            id, customer_id, number, amount::numeric, currency,
            status, description, due_date, paid_at, created_at, updated_at
        FROM invoices
        WHERE id = $1 AND status = 'open'
        FOR UPDATE
        "#,
        invoice_id
    )
    .fetch_optional(&mut *tx)
    .await?
    .ok_or_else(|| AppError::NotFound("Invoice not found or not open".into()))?;
    
    // Record the payment
    let now = Utc::now();
    sqlx::query!(
        r#"
        INSERT INTO payments (
            invoice_id, amount, method, transaction_id, 
            status, processed_at, created_at
        )
        VALUES ($1, $2, $3, $4, 'success', $5, $6)
        "#,
        invoice_id,
        invoice.amount,
        payment_method,
        transaction_id,
        now,
        now
    )
    .execute(&mut *tx)
    .await?;
    
    // Update the invoice
    let updated_invoice = sqlx::query_as!(
        Invoice,
        r#"
        UPDATE invoices
        SET status = 'paid', paid_at = $2, updated_at = $2
        WHERE id = $1
        RETURNING 
            id, customer_id, number, amount::numeric, currency,
            status, description, due_date, paid_at, created_at, updated_at
        "#,
        invoice_id,
        now
    )
    .fetch_one(&mut *tx)
    .await?;
    
    // Commit the transaction
    tx.commit().await?;
    
    // Send notification (outside transaction)
    self.notification_service.send_invoice_paid_notification(invoice_id).await?;
    
    Ok(updated_invoice)
}
```

</examples>

<troubleshooting>

## Common Transaction Errors

### Immutable Transaction Reference
- "the trait `sqlx::Executor<'_>` is not implemented for `&PgConnection`"
  - Cause: Using `&*tx` instead of `&mut *tx` when executing queries
  - Solution: Use mutable reference `&mut *tx` for all query executions

### Transaction Already Finished
- "Transaction already finished"
  - Cause: Trying to use a transaction after it has been committed or rolled back
  - Solution: Never use a transaction after commit or rollback

### Dropped Transactions Without Commit/Rollback
- "Dropping a Transaction without committing or rolling back"
  - Cause: Allowing a transaction to go out of scope without explicit finalization
  - Solution: Always explicitly commit or roll back transactions

### Nested Transactions
- "Cannot begin a transaction within a transaction"
  - Cause: Attempting to start a new transaction while already in one
  - Solution: Use savepoints for nested transaction-like behavior

### Connection Pool Exhaustion
- "Timeout waiting for a connection from the pool"
  - Cause: Keeping transactions open for too long
  - Solution: Keep transactions as short as possible and release connections promptly

## Debugging Tips
- Add logging at transaction boundaries (begin, commit, rollback)
- Use transaction tracking in development to detect leaked transactions
- Monitor database locks during transactions
- Check transaction isolation levels for concurrency issues
- Implement timeout handling for long-running transactions

</troubleshooting>
