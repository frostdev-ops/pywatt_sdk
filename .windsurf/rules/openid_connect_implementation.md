---
trigger: model_decision
description: This rule documents specific implementation details and best practices for handling OpenID Connect (OIDC) in the PyWatt-Rust project, focusing on proper client setup, endpoint configuration, and method usage.
globs: 
---
# OpenID Connect Implementation

<context>
This rule documents specific implementation details and best practices for handling OpenID Connect (OIDC) in the PyWatt-Rust project, focusing on proper client setup, endpoint configuration, and method usage.
</context>

<rules>

## Client Type Selection
- Use `CoreClient` from openidconnect for OIDC providers (e.g., Google)
- Use `BasicClient` from oauth2 for OAuth2-only providers (e.g., GitHub)
- Never mix method calls between OIDC and OAuth2 clients

## Endpoint Configuration
- For OIDC, use `CoreProviderMetadata::discover_async()` to fetch provider metadata
- Set up clients with the correct endpoint types: use `set_user_info_url()` (not `set_userinfo_url()`)
- For OIDC, ensure all required endpoints are properly configured:
  - Authorization endpoint
  - Token endpoint
  - User info endpoint
  - JWKS URI

## Authorization Flow
- For OIDC, use `AuthenticationFlow::<CoreResponseType>::AuthorizationCode` as the flow type
- Always include a nonce for OIDC flows, using `|| nonce.clone()` closure syntax
- Use state parameter with `|| state.clone()` closure syntax for CSRF protection

## Token Exchange
- For OIDC, verify ID tokens using the client's `id_token_verifier()` method
- Verify access token hash when available in the ID token
- Use the correct HTTP client for each protocol: `oidc_async_http_client` for OIDC, `async_http_client` for OAuth2

## User Info Retrieval
- Access OIDC provider metadata with `client.provider_metadata()`
- Access user info endpoint with `provider_metadata.userinfo_endpoint()`

</rules>

<patterns>

## OIDC Client Setup with Discovery
```rust
// Fetch provider metadata
let issuer_url = IssuerUrl::new("https://accounts.google.com".to_string())?;
let provider_metadata = CoreProviderMetadata::discover_async(
    issuer_url, 
    oidc_async_http_client
).await?;

// Create client with metadata
let client = CoreClient::from_provider_metadata(
    provider_metadata,
    OidcClientId::new(client_id),
    Some(OidcClientSecret::new(client_secret)),
)
.set_redirect_uri(OidcRedirectUrl::new(redirect_uri)?);
```

## OIDC Authorization URL Generation
```rust
// Generate PKCE challenge, state, and nonce
let (pkce_challenge, pkce_verifier) = PkceCodeChallenge::new_random_sha256();
let state = CsrfToken::new_random();
let nonce = Nonce::new_random();

// Generate authorization URL
let auth_url = client
    .authorize_url(
        AuthenticationFlow::<CoreResponseType>::AuthorizationCode,
        || state.clone(),
        || nonce.clone()
    )
    .set_pkce_challenge(pkce_challenge)
    .add_scope(Scope::new("profile".to_string()))
    .add_scope(Scope::new("email".to_string()))
    .url();
```

## OIDC Token Exchange and Validation
```rust
// Exchange code for tokens
let token_response = client
    .exchange_code(code)
    .set_pkce_verifier(pkce_verifier)
    .request_async(oidc_async_http_client)
    .await?;

// Verify ID token
let id_token = token_response.id_token()
    .ok_or_else(|| AppError::OAuthCodeExchangeFailed("No ID token in response".to_string()))?;

let claims = id_token.claims(&client.id_token_verifier(), &nonce)?;
```

## User Info Retrieval
```rust
// Get provider metadata
if let Some(provider_metadata) = client.provider_metadata() {
    // Check if user info endpoint is available
    if let Some(userinfo_url) = provider_metadata.userinfo_endpoint() {
        // Create client with user info URL
        let userinfo_client = client.clone()
            .set_user_info_url(userinfo_url.clone());
        
        // Create and send user info request
        let userinfo = userinfo_client
            .userinfo(token_response.access_token().clone(), None)
            .request_async(oidc_async_http_client)
            .await?;
        
        // Process user info claims
        // ...
    }
}
```

</patterns>

<examples>

## Complete OIDC Flow Implementation
```rust
/// Handles the entire OpenID Connect flow for Google authentication
pub async fn authenticate_with_google(
    &self,
    code: String,
    state: String,
    session_state: String
) -> AppResult<User> {
    // Verify state to prevent CSRF
    if state != session_state {
        return Err(AppError::InvalidToken("OIDC state mismatch".to_string()));
    }
    
    // Create OIDC client
    let client = create_oidc_client("google", &self.settings).await?;
    
    // Retrieve stored PKCE verifier and nonce from session
    let (pkce_verifier, nonce) = self.session_service
        .get_oidc_auth_data(&session_id)
        .await?;
    
    // Exchange code for tokens
    let token_response = client
        .exchange_code(AuthorizationCode::new(code))
        .set_pkce_verifier(pkce_verifier)
        .request_async(oidc_async_http_client)
        .await?;
    
    // Verify ID token
    let id_token = token_response.id_token()
        .ok_or_else(|| AppError::OAuthCodeExchangeFailed("No ID token in response".to_string()))?;
    
    let claims = id_token.claims(&client.id_token_verifier(), &nonce)?;
    
    // Extract user info
    let email = claims.email()
        .ok_or_else(|| AppError::OAuthUserInfoFailed("Missing email claim".to_string()))?
        .to_string();
    
    let name = claims.name().map(|n| n.to_string());
    let subject = claims.subject().to_string();
    
    // Get additional user info if available
    let additional_info = if let Some(provider_metadata) = client.provider_metadata() {
        if let Some(userinfo_url) = provider_metadata.userinfo_endpoint() {
            let userinfo_client = client.clone().set_user_info_url(userinfo_url.clone());
            
            let user_info = userinfo_client
                .userinfo(token_response.access_token().clone(), None)
                .request_async(oidc_async_http_client)
                .await
                .ok();
                
            // Process additional user info
            // ...
            Some(user_info)
        } else {
            None
        }
    } else {
        None
    };
    
    // Find or create user
    self.user_service.find_or_create_oauth_user(
        "google",
        subject,
        email,
        name,
    ).await
}
```

## OIDC Client Creation with Error Handling
```rust
/// Create an OpenID Connect client for Google
pub async fn create_google_oidc_client(
    client_id: String,
    client_secret: SecretString,
    redirect_uri: String
) -> AppResult<CoreClient> {
    // Google's OIDC discovery endpoint
    let issuer_url = IssuerUrl::new("https://accounts.google.com".to_string())
        .map_err(|e| AppError::InvalidConfiguration(format!("Invalid issuer URL: {}", e)))?;
    
    // Fetch provider metadata with detailed error handling
    let provider_metadata = match CoreProviderMetadata::discover_async(
        issuer_url.clone(),
        oidc_async_http_client
    ).await {
        Ok(metadata) => metadata,
        Err(e) => {
            error!("Failed to discover OIDC provider metadata: {}", e);
            return Err(AppError::InvalidConfiguration(
                format!("Failed to discover OIDC provider metadata for Google: {}", e)
            ));
        }
    };
    
    // Verify that all required endpoints are present
    if provider_metadata.token_endpoint().is_none() {
        return Err(AppError::InvalidConfiguration(
            "Google OIDC metadata missing token endpoint".to_string()
        ));
    }
    
    if provider_metadata.authorization_endpoint().is_none() {
        return Err(AppError::InvalidConfiguration(
            "Google OIDC metadata missing authorization endpoint".to_string()
        ));
    }
    
    // Create client with validated metadata
    let client_id = OidcClientId::new(client_id);
    let client_secret = OidcClientSecret::new(client_secret.expose_secret().clone());
    let redirect_url = OidcRedirectUrl::new(redirect_uri)
        .map_err(|e| AppError::InvalidConfiguration(format!("Invalid redirect URL: {}", e)))?;
    
    let client = CoreClient::from_provider_metadata(
        provider_metadata, 
        client_id,
        Some(client_secret),
    )
    .set_redirect_uri(redirect_url);
    
    Ok(client)
}
```

</examples>

<troubleshooting>

## Common Errors

### Method Not Found Errors
- "no method named `exchange_code` found for struct `CoreClient<...>`"
  - Cause: Client not properly configured with token endpoint
  - Solution: Ensure client is created with proper metadata or configure with `set_token_endpoint`

- "no method named `provider_metadata` found for reference `&CoreClient<...>`"
  - Cause: Trying to access provider metadata on a client not created from metadata
  - Solution: Use `CoreClient::from_provider_metadata` when creating the client

- "no method named `set_userinfo_url` found for struct `CoreClient`"
  - Cause: Method name mismatch, should be `set_user_info_url` (note the underscore)
  - Solution: Use the correct method name `set_user_info_url`

### Type Mismatch Errors
- "expected `EndpointNotSet`, found `EndpointSet`"
  - Cause: Returning a client with configured endpoints where a client with unset endpoints is expected
  - Solution: Ensure return type matches the client configuration state

- "expected struct `openidconnect::Client<..., EndpointNotSet, ...>`, found struct `openidconnect::Client<..., EndpointSet, ...>`"
  - Cause: Type mismatch due to endpoint configuration
  - Solution: Revise the function signature to match the actual client type

### Authorization URL Errors
- "no method named `authorize_url` found for struct `CoreClient<...>`"
  - Cause: Client not properly configured with authorization endpoint
  - Solution: Ensure client is created with proper metadata or configure with `set_auth_url`

## General Troubleshooting
- Check that all required endpoints are properly configured
- Verify that you're using the correct client type for the protocol (OAuth2 vs OIDC)
- Ensure all required parameters are passed to client methods
- Check for proper closures when generating auth URLs (`|| state.clone()` vs `state.clone()`)

</troubleshooting>
