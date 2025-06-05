---
trigger: model_decision
description: This rule defines the standard pattern for handling updates to entities with optional fields in service methods within the PyWatt-Rust project, particularly in the `finance_service` module.
globs: 
---
# Cursor Rule: update_optional_fields

<context>
This rule defines the standard pattern for handling updates to entities with optional fields in service methods within the PyWatt-Rust project, particularly in the `finance_service` module.
</context>

<rules>

## Pattern: Fetch-Merge-Update

When implementing an `update_*` method that takes an `Update*Request` struct containing `Option<T>` fields, follow these steps:

1.  **Fetch Existing Entity**: Retrieve the current state of the entity from the database using its ID. Handle the case where the entity is not found (e.g., return `Ok(None)` or `Err(sqlx::Error::RowNotFound)`).
2.  **Merge Optional Fields**: Iterate through each field in the `Update*Request` struct. If a field is `Some(value)`, update the corresponding field in the fetched entity struct.
    - For `Option<T>` fields in the entity struct, assign `Some(value)`.
    - For non-optional fields in the entity struct, assign `value` directly.
3.  **Update Timestamp**: Set the `updated_at` field on the merged entity struct to the current time (`Utc::now()`).
4.  **Execute SQL UPDATE**: Perform the database update using the merged entity struct.
    - The `SET` clause should include all updatable fields, including `updated_at`.
    - Bind values from the merged entity struct.
    - Use `RETURNING *` (or specific columns) to get the updated entity state.
5.  **Return Updated Entity**: Return the entity returned by the `UPDATE ... RETURNING` query.

## Example (`update_client` in `ClientService`)
```rust
use crate::models::{Client, UpdateClientRequest};
use sqlx::PgPool;
use uuid::Uuid;
use chrono::Utc;

// Assuming ClientService and get_client method exist

pub async fn update_client(
    pool: &PgPool, // Example: Pass pool directly or use self.pool
    req: UpdateClientRequest
) -> Result<Client, sqlx::Error> {
    // 1. Fetch Existing Entity
    let mut client = sqlx::query_as!(
        Client, 
        "SELECT ... FROM clients WHERE id = $1", 
        req.id
    )
    .fetch_optional(pool)
    .await?
    .ok_or(sqlx::Error::RowNotFound)?;

    // 2. Merge Optional Fields
    if let Some(name) = req.name { client.name = name; }
    if let Some(email) = req.email { client.email = Some(email); } // Entity field is Option<String>
    if let Some(phone) = req.phone { client.phone = Some(phone); }
    // ... merge other optional fields ...
    if let Some(status) = req.status { client.status = status; } // Entity field is String
    if let Some(owner_id) = req.owner_id { client.owner_id = owner_id; }

    // 3. Update Timestamp
    let now = Utc::now();
    client.updated_at = now;

    // 4. Execute SQL UPDATE
    let updated = sqlx::query_as!(
        Client,
        r#"
        UPDATE clients
        SET 
            name = $1, email = $2, phone = $3, -- ... other fields ...
            status = $10, owner_id = $18, 
            updated_at = $19
        WHERE id = $20
        RETURNING 
            id, name, email, phone, -- ... all fields ... 
            created_at, updated_at, status, owner_id, user_id
        "#,
        client.name, client.email, client.phone, // ... bind other fields ...
        client.status, client.owner_id, 
        client.updated_at, // Bind the timestamp
        client.id
    )
    .fetch_one(pool)
    .await?;
    
    // 5. Return Updated Entity (adjust if non-DB fields need handling)
    Ok(Client { invoices: None, ..updated })
}
```

## Rationale

- **Atomicity**: While the fetch and update are separate operations, this pattern is common for partial updates.
- **Clarity**: Explicitly merging fields in Rust code is clearer than complex SQL `COALESCE` or conditional updates for many fields.
- **Validation**: Allows for potential validation logic between fetching and updating.
- **Consistency**: Ensures `updated_at` is always set.

## Alternative (`COALESCE`)

For simple updates involving only a few fields, using `COALESCE` directly in the SQL `SET` clause can be an alternative, but it becomes unwieldy for many optional fields.

```sql
UPDATE my_table
SET 
    field1 = COALESCE($1, field1),
    field2 = COALESCE($2, field2),
    updated_at = NOW()
WHERE id = $3
RETURNING *
```

Prefer the Fetch-Merge-Update pattern for consistency and clarity when dealing with multiple optional fields.

</rules> 
