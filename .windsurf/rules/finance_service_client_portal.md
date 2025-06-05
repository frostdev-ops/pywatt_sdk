---
trigger: model_decision
description: This component implements a client portal API in the Finance Service module.
globs: 
---
# Component: Finance Service Client Portal

## Component Type
API Controller

## File Path
`src/modules/finance_service/src/main.rs` (handlers)

## Purpose
This component implements a client portal API in the Finance Service module. It provides functionality to:
- Display a dashboard of client-specific financial data (invoices, estimates, proposals, contracts)
- Allow clients to pay invoices through Stripe Checkout
- Provide a secure interface for client self-service

## Key Types & Structures
- None specific to this component (uses existing finance models and services)

## Interfaces/Traits
- **Dashboard Aggregation**: Collects and returns client-specific financial data
- **Payment Initiation**: Creates Stripe checkout sessions for client invoice payments

## Public API
- **`GET /v1/finance/portal/clients/:client_id/dashboard`**: Retrieves aggregated client data
- **`POST /v1/finance/portal/clients/:client_id/invoices/:id/pay`**: Creates a payment checkout session

## Design Patterns
- **API Gateway**: Portal endpoints act as an aggregation layer over underlying services
- **Resource-based Authorization**: Routes include client_id to enforce proper access control

## Error Handling
- Invoice not found returns 404 Not Found
- Accessing another client's data returns 403 Forbidden
- Service errors return 500 Internal Server Error

## Usage Examples
```rust
// Get client dashboard data
let response = await fetch("/v1/finance/portal/clients/1234/dashboard", {
  headers: { "Authorization": "Bearer token" }
});
const dashboard = await response.json();
// Contains proposals, estimates, invoices, contracts

// Pay an invoice
let response = await fetch("/v1/finance/portal/clients/1234/invoices/5678/pay", {
  method: "POST",
  headers: { "Authorization": "Bearer token" }
});
const { session_id } = await response.json();
```

## Testing Approach
- **Integration Tests**: Test portal endpoints with mock services
- **E2E Tests**: Verify full client portal flow from login through dashboard to payment

## Dependencies
- **Internal**: ClientService, InvoiceService, EstimateService, ProposalService, ContractService, StripeService
- **External**: None (client-side UI would integrate with these APIs)

## Rust-Specific Features
- **Path Extraction**: Using Axum's Path extractor to get client_id and invoice_id
- **Async/Await**: All portal handlers are async for efficient service composition

## Performance Considerations
- Dashboard endpoint makes multiple service calls - could be optimized with parallelism
- Consider caching for dashboard data that doesn't change frequently

## Security Considerations
- JWT authentication required for all portal endpoints
- Client ID in URL path should match authenticated user's permitted clients
- Rate limiting may be needed to prevent abuse

## Notes & Best Practices
- The portal API is designed to be consumed by a separate frontend application
- Future enhancements could include real-time notifications or a WebSocket interface
- Consider adding pagination for clients with many financial records
