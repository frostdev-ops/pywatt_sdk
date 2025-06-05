---
trigger: model_decision
description: This component manages subscription plans and customer subscriptions in the Finance Service module. 
globs: 
---
# Component: Finance Service Subscription Management

## Component Type
Service/API Controller

## File Path
`src/modules/finance_service/src/services/subscription_service.rs`
`src/modules/finance_service/src/main.rs` (handlers)

## Purpose
This component manages subscription plans and customer subscriptions in the Finance Service module. It provides functionality to:
- Create and manage subscription plans with different price points
- Subscribe clients to plans and manage their subscription lifecycle
- Record Stripe subscription IDs for external payment processing integration

## Key Types & Structures
- **`SubscriptionPlan`**: Model representing a subscription plan with name, price, and currency
- **`Subscription`**: Model representing a client's subscription to a specific plan
- **`CreateSubscriptionPlanRequest`**: Payload for creating a new subscription plan
- **`CreateSubscriptionRequest`**: Payload for subscribing a client to a plan
- **`UpdateSubscriptionRequest`**: Payload for updating a subscription's status or end date

## Interfaces/Traits
- **Plan Management**: Create, list, and manage subscription plans
- **Subscription Management**: Subscribe clients to plans, update status, and manage lifecycle

## Public API
- **`POST /v1/finance/subscription_plans`**: Create a new subscription plan
- **`GET /v1/finance/subscription_plans`**: List all subscription plans
- **`POST /v1/finance/subscriptions`**: Subscribe a client to a plan
- **`GET /v1/finance/subscriptions`**: List all active subscriptions
- **`GET /v1/finance/subscriptions/:id`**: Get a specific subscription
- **`PUT /v1/finance/subscriptions/:id`**: Update a subscription's status or end date

## Design Patterns
- **Repository Pattern**: Service methods map closely to database operations
- **Data Transfer Objects**: Request/response payloads separate from internal models

## Error Handling
- Database errors are logged and returned as 500 Internal Server Error
- Not found subscription returns 404 Not Found
- Invalid operation (e.g., subscribing to non-existent plan) returns 400 Bad Request

## Usage Examples
```rust
// Creating a subscription plan
let plan_request = CreateSubscriptionPlanRequest {
    name: "Premium Plan",
    price_cents: 1999,
    currency: "USD",
};
let plan = subscription_service.create_plan(plan_request).await?;

// Subscribing a client
let subscription_request = CreateSubscriptionRequest {
    client_id: client.id, 
    plan_id: plan.id,
};
let subscription = subscription_service.create_subscription(subscription_request).await?;
```

## Testing Approach
- **Unit Tests**: Test subscription CRUD operations with mock database
- **Integration Tests**: Verify database operations with actual schema

## Dependencies
- **Internal**: Database, Client records
- **External**: None (Stripe integration is separate)

## Rust-Specific Features
- **SQLx Query Macros**: Strongly-typed database operations
- **Option Types**: Handling nullable fields like end_date
- **NaiveDate**: Managing date fields for subscription periods

## Performance Considerations
- Subscription queries are relatively low-volume and infrequent
- Keeping subscription data in the same database as other finance data simplifies transactions

## Security Considerations
- Subscription operations require JWT authentication
- Only authorized users can create plans or modify subscriptions

## Notes & Best Practices
- Stripe integration for recurring billing would be added in a future phase
- Keep subscription status updated when payment events occur
- Consider adding hooks to notify clients of subscription changes (emails, etc.)
