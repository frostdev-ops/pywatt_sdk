---
trigger: model_decision
description: The data models define the core domain entities and their relationships in the application. They provide type-safe representations of data structures used throughout the system, from database interactions to API responses.
globs: 
---
# Data Models

## Purpose
The data models define the core domain entities and their relationships in the application. They provide type-safe representations of data structures used throughout the system, from database interactions to API responses.

## Key Types & Structures
```rust
// User Management
#[derive(Debug, Serialize, Deserialize, sqlx::FromRow)]
pub struct User {
    pub id: Uuid,
    pub email: String,
    pub password_hash: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub verified: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct UserProfile {
    pub user_id: Uuid,
    pub display_name: String,
    pub avatar_url: Option<String>,
    pub bio: Option<String>,
}

// Authentication & Authorization
#[derive(Debug, Serialize, Deserialize)]
pub struct ApiKey {
    pub id: Uuid,
    pub user_id: Uuid,
    pub key: String,
    pub name: String,
    pub expires_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Role {
    pub id: Uuid,
    pub name: String,
    pub permissions: Vec<String>,
}

// Chat & Messaging
#[derive(Debug, Serialize, Deserialize)]
pub struct Conversation {
    pub id: Uuid,
    pub title: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Message {
    pub id: Uuid,
    pub conversation_id: Uuid,
    pub sender_id: Uuid,
    pub content: String,
    pub sent_at: DateTime<Utc>,
    pub metadata: Option<JsonValue>,
}

// Document Management
#[derive(Debug, Serialize, Deserialize)]
pub struct Document {
    pub id: Uuid,
    pub owner_id: Uuid,
    pub title: String,
    pub content: String,
    pub version: i32,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct DocumentShare {
    pub id: Uuid,
    pub document_id: Uuid,
    pub user_id: Uuid,
    pub permission_level: SharePermission,
    pub expires_at: Option<DateTime<Utc>>,
}

// Business Models
#[derive(Debug, Serialize, Deserialize)]
pub struct Customer {
    pub id: Uuid,
    pub name: String,
    pub email: String,
    pub phone: Option<String>,
    pub address: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Product {
    pub id: Uuid,
    pub name: String,
    pub description: String,
    pub price: Decimal,
    pub active: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Invoice {
    pub id: Uuid,
    pub customer_id: Uuid,
    pub amount: Decimal,
    pub status: InvoiceStatus,
    pub due_date: DateTime<Utc>,
    pub items: Vec<InvoiceItem>,
}
```

## Model Categories
### User & Authentication
```rust
// New user registration
#[derive(Debug, Validate)]
pub struct NewUser {
    #[validate(email)]
    pub email: String,
    #[validate(length(min = 8))]
    pub password: String,
}

// Login credentials
#[derive(Debug)]
pub struct LoginCredentials {
    pub email: String,
    pub password: String,
    pub totp_code: Option<String>,
}

// Session management
#[derive(Debug)]
pub struct Session {
    pub id: Uuid,
    pub user_id: Uuid,
    pub expires_at: DateTime<Utc>,
    pub metadata: SessionMetadata,
}
```

### Business Logic
```rust
// Invoice processing
#[derive(Debug)]
pub struct InvoiceItem {
    pub product_id: Uuid,
    pub quantity: i32,
    pub unit_price: Decimal,
    pub subtotal: Decimal,
}

// Payment processing
#[derive(Debug)]
pub struct Payment {
    pub id: Uuid,
    pub invoice_id: Uuid,
    pub amount: Decimal,
    pub status: PaymentStatus,
    pub provider: PaymentProvider,
    pub metadata: JsonValue,
}
```

### Chat & Documents
```rust
// Message types
#[derive(Debug)]
pub enum MessageType {
    Text,
    System,
    Error,
    Action,
}

// Document sharing
#[derive(Debug)]
pub enum SharePermission {
    Read,
    Write,
    Admin,
}
```

## Design Patterns
### Active Record Pattern
- **Purpose**: Maps database rows to objects
- **Implementation**: Uses `sqlx::FromRow`
- **Usage**: Database query results to structs

### Data Transfer Objects
- **Purpose**: API request/response structures
- **Implementation**: Separate from database models
- **Usage**: Input/output data validation

### Builder Pattern
- **Purpose**: Complex object construction
- **Implementation**: Builder structs
- **Usage**: Optional fields and validation

## Validation
```rust
#[derive(Debug, Validate)]
pub struct NewCustomer {
    #[validate(length(min = 1))]
    pub name: String,
    
    #[validate(email)]
    pub email: String,
    
    #[validate(phone)]
    pub phone: Option<String>,
}

impl NewCustomer {
    pub fn validate(&self) -> Result<(), ValidationError> {
        use validator::Validate;
        self.validate()?;
        Ok(())
    }
}
```

## Testing Approach
### Unit Tests
```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_new_user_validation() {
        let user = NewUser {
            email: "invalid".into(),
            password: "short".into(),
        };
        
        assert!(user.validate().is_err());
    }
}
```

### Property Tests
```rust
#[cfg(test)]
mod tests {
    use proptest::prelude::*;
    
    proptest! {
        #[test]
        fn test_invoice_total_calculation(items in vec((1..100i32, 1..1000i32), 1..10)) {
            let invoice_items: Vec<InvoiceItem> = items
                .into_iter()
                .map(|(qty, price)| InvoiceItem {
                    quantity: qty,
                    unit_price: Decimal::from(price),
                    ..Default::default()
                })
                .collect();
                
            let invoice = Invoice::new(invoice_items);
            assert!(invoice.total() > Decimal::zero());
        }
    }
}
```

## Dependencies
### Internal Dependencies
- `errors.rs`: Error types
- `utils/*`: Helper functions
- `validation/*`: Custom validators

### External Dependencies
- `serde`: Serialization
- `validator`: Input validation
- `sqlx`: Database mapping
- `chrono`: Date/time types

## Notes & Best Practices
### Performance Considerations
- Efficient serialization
- Minimal cloning
- Smart pointers usage
- Derive vs manual impl

### Security Considerations
- Password hashing
- Input sanitization
- Data validation
- Access control

### Rust Idioms
- Type safety
- Error handling
- Trait implementations
- Builder patterns

### Maintenance Notes
- Document relationships
- Version migrations
- Backward compatibility
- Test coverage

## Related Components
- `services/*`: Business logic
- `routes/*`: API endpoints
- `schemas/*`: API schemas
- `migrations/*`: Database schema
