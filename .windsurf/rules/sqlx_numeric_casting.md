---
trigger: manual
description:
globs:
---
# SQLX Numeric and Float Casting

<context>
This rule documents best practices for handling numeric types (particularly f64 and Decimal) in SQLx queries within the PyWatt-Rust project, focusing on proper type casting to avoid conversion errors.
</context>

<rules>

## Type Casting in SQL Queries
- Always use explicit type casting (::float8, ::numeric) when returning decimal or floating-point values in SQLx queries
- For f64 values, use `::float8` in the SQL query to ensure proper Rust type conversion
- For Decimal values, use `::numeric` in the SQL query and enable the sqlx `bigdecimal` feature in Cargo.toml
- Never return raw numeric database values without explicit casting

## Feature Requirements
- Ensure the sqlx `bigdecimal` feature is enabled in Cargo.toml when working with numeric values
- Use rust_decimal for high-precision financial calculations in application code
- For f64 database fields, ensure proper features are enabled in sqlx configuration

## Handling NULL Values
- Always use Option<f64> or Option<Decimal> for nullable database fields
- Use COALESCE in SQL queries to handle NULL values properly
- Be cautious with NULL handling in aggregate functions (SUM, AVG)

## Testing and Validation
- Write tests that specifically check numeric precision requirements
- Validate calculations match expected financial precision needs
- Test edge cases including NULL values and boundary conditions

</rules>

<patterns>

## Proper f64 Value Casting
```rust
// Use ::float8 for f64 values
let value = sqlx::query_scalar!(
    r#"
    SELECT amount::float8
    FROM invoices
    WHERE id = $1
    "#,
    invoice_id
)
.fetch_one(&pool)
.await?;
```

## Proper Decimal Value Casting
```rust
// Use ::numeric for Decimal values
let value = sqlx::query_scalar!(
    r#"
    SELECT amount::numeric
    FROM invoices
    WHERE id = $1
    "#,
    invoice_id
)
.fetch_one(&pool)
.await?;
```

## Handling NULL Values in Numeric Operations
```rust
// Use COALESCE for NULL handling
let total = sqlx::query_scalar!(
    r#"
    SELECT COALESCE(SUM(amount), 0)::float8 as total
    FROM payments
    WHERE customer_id = $1
    "#,
    customer_id
)
.fetch_one(&pool)
.await?;
```

## Returning Typed Numeric Values in Queries
```rust
// Use proper type casting in complex queries
let invoice = sqlx::query_as!(
    Invoice,
    r#"
    SELECT 
        id, 
        customer_id, 
        number, 
        amount::float8, 
        status,
        created_at
    FROM invoices
    WHERE id = $1
    "#,
    invoice_id
)
.fetch_one(&pool)
.await?;
```

</patterns>

<examples>

## Complete Example with f64 Fields
```rust
pub async fn get_invoice_with_calculations(
    &self,
    invoice_id: Uuid,
) -> AppResult<InvoiceDetails> {
    // Get the invoice with proper numeric casting
    let invoice = sqlx::query_as!(
        Invoice,
        r#"
        SELECT 
            id, 
            customer_id, 
            number, 
            amount::float8, 
            tax_rate::float8,
            status
        FROM invoices
        WHERE id = $1
        "#,
        invoice_id
    )
    .fetch_one(&self.pool)
    .await?;
    
    // Get the line items with proper numeric casting
    let items = sqlx::query_as!(
        LineItem,
        r#"
        SELECT 
            id, 
            invoice_id, 
            description, 
            quantity::float8, 
            unit_price::float8,
            (quantity * unit_price)::float8 as subtotal
        FROM invoice_line_items
        WHERE invoice_id = $1
        "#,
        invoice_id
    )
    .fetch_all(&self.pool)
    .await?;
    
    // Calculate totals
    let subtotal: f64 = items.iter().map(|item| item.subtotal.unwrap_or(0.0)).sum();
    let tax = subtotal * (invoice.tax_rate.unwrap_or(0.0) / 100.0);
    let total = subtotal + tax;
    
    Ok(InvoiceDetails {
        invoice,
        items,
        subtotal,
        tax,
        total,
    })
}
```

## Handling Decimal to f64 Conversion
```rust
pub async fn get_account_balance(
    &self,
    account_id: Uuid,
) -> AppResult<f64> {
    // Query with explicit casting to float8
    let balance = sqlx::query_scalar!(
        r#"
        SELECT 
            COALESCE(
                (
                    SELECT SUM(amount)::float8 
                    FROM deposits 
                    WHERE account_id = $1
                ), 
                0.0
            ) -
            COALESCE(
                (
                    SELECT SUM(amount)::float8 
                    FROM withdrawals 
                    WHERE account_id = $1
                ), 
                0.0
            ) as balance
        "#,
        account_id
    )
    .fetch_one(&self.pool)
    .await?;
    
    // Handle potential NULL (though our COALESCE should prevent this)
    Ok(balance.unwrap_or(0.0))
}
```

</examples>

<troubleshooting>

## Common Errors

### Type Conversion Errors
- "the trait bound `f64: std::convert::From<()>` is not satisfied"
  - Cause: Missing type casting in SQL query
  - Solution: Add `::float8` to numeric fields in the query

- "optional sqlx feature `bigdecimal` required for type NUMERIC"
  - Cause: Missing sqlx feature for numeric handling
  - Solution: Add "bigdecimal" to sqlx features in Cargo.toml

### Null Value Errors
- "called `Option::unwrap()` on a `None` value"
  - Cause: Database returned NULL for a numeric field
  - Solution: Use Option<f64> for nullable fields or COALESCE in SQL

### Precision Loss
- Unexpected rounding or precision loss in financial calculations
  - Cause: Using f64 for financial data that requires exact precision
  - Solution: Use rust_decimal::Decimal for financial calculations

## Debugging Tips
- Add debug logging for numeric values to check precision
- Check SQL query execution with explicit type information
- Use PostgreSQL's type conversion functions in complex queries
- For financial calculations, compare results with manual calculations

</troubleshooting>
