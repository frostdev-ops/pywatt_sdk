---
trigger: model_decision
description: This rule documents the fields of the `Client` struct in the `finance_service` module, aligning with the database schema defined in migration 
globs: 
---
# Cursor Rule: models_client_fields

<context>
This rule documents the fields of the `Client` struct in the `finance_service` module, aligning with the database schema defined in migration `0012_add_client_details.sql`.
</context>

<rules>

## Field Descriptions

- `id: Uuid`: Primary key, unique identifier for the client.
- `name: String`: The legal or display name of the client.
- `email: Option<String>`: Primary contact email address for the client.
- `phone: Option<String>`: Primary contact phone number for the client.
- `address: Option<String>`: Street address of the client.
- `city: Option<String>`: City where the client is located.
- `state: Option<String>`: State or province where the client is located.
- `zip: Option<String>`: Postal code for the client's address.
- `country: Option<String>`: Country where the client is located.
- `notes: Option<String>`: Internal notes or additional information about the client.
- `created_at: DateTime<Utc>`: Timestamp when the client record was created.
- `updated_at: DateTime<Utc>`: Timestamp when the client record was last updated.
- `status: String`: Current status of the client (e.g., 'active', 'inactive', 'lead'). Default is 'active'.
- `client_type: Option<String>`: Categorization of the client (e.g., 'individual', 'company', 'non-profit').
- `industry: Option<String>`: Industry the client operates in.
- `website: Option<String>`: URL of the client's website.
- `tax_id: Option<String>`: Client's tax identification number (e.g., EIN, VAT ID).
- `currency: String`: Default currency for transactions with this client (e.g., 'USD', 'EUR'). Default is 'USD'.
- `payment_terms: Option<String>`: Standard payment terms agreed upon (e.g., 'Net 30', 'Due on receipt').
- `payment_method: Option<String>`: Client's preferred or default payment method.
- `owner_id: Uuid`: Foreign key referencing the `users` table. Identifies the primary internal user (employee) responsible for managing this client relationship.
- `user_id: Uuid`: Foreign key referencing the `users` table. Could represent the client's user account if they have portal access, or another associated user.

## Non-Database Fields (Loaded Separately)

These fields are part of the struct but are typically populated through separate queries or relations, not directly mapped by `sqlx::FromRow` from the `clients` table itself.

- `invoices: Option<Vec<Invoice>>`: Associated invoices.
- `estimates: Option<Vec<Estimate>>`: Associated estimates.
- `payments: Option<Vec<Payment>>`: Associated payments.
- `proposals: Option<Vec<Proposal>>`: Associated proposals.
- `contracts: Option<Vec<Contract>>`: Associated contracts.

## Usage

- Use this struct when fetching client data from the database via `sqlx::query_as!`.
- Ensure all non-optional fields (`id`, `name`, `created_at`, `updated_at`, `status`, `currency`, `owner_id`, `user_id`) have corresponding `NOT NULL` columns in the database.
- Optional fields correspond to nullable database columns.

</rules>
