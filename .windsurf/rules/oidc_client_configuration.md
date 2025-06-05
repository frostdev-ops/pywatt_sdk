---
trigger: model_decision
description: This rule documents common patterns and best practices for configuring and using OpenID Connect clients in the PyWatt-Rust project, focusing on proper client setup, endpoint configuration, and correct method usage.
globs: 
---
# OpenID Connect Client Configuration

<context>
This rule documents common patterns and best practices for configuring and using OpenID Connect clients in the PyWatt-Rust project, focusing on proper client setup, endpoint configuration, and correct method usage.
</context>

<rules>

## Client Type Selection
- Use `CoreClient` from openidconnect for OIDC flows
- Use `BasicClient` from oauth2 for OAuth2-only flows
- Never mix method calls between OIDC and OAuth2 clients
- Use the appropriate HTTP client for each: `oidc_async_http_client` for OIDC, `async_http_client` for OAuth2

## Client Construction
- Always use `CoreProviderMetadata::discover_async()` to fetch OIDC provider metadata
- Create clients using `CoreClient::from_provider_metadata()` to ensure all endpoints are properly configured
- Set redirect URIs with `set_redirect_uri()` after creating the client
- Verify all required endpoints are available in the metadata before using them

## Method Usage
- For user info retrieval, use `user_info()` (not `userinfo()`) on OIDC clients
- For authorization URL generation, use the correct flow type: `AuthenticationFlow::<CoreResponseType>::AuthorizationCode`
- Always provide nonce and state as closures: `|| nonce.clone()`, `|| state.clone()`
- When working with ID tokens, verify them using `id_token.claims(&client.id_token_verifier(), &nonce)`

## Error Handling
- Handle discovery errors explicitly, providing clear error messages
- Verify ID tokens and their claims systematically
- Check for required endpoints before using them
- Implement proper error types for different OIDC error scenarios

</rules>

<patterns>

## OIDC Client Construction
```rust
/// Create an OpenID Connect client for Google
pub async fn create_oidc_client(
    provider_name: &str,
    settings: &Settings,
) -> AppResult<CoreClient> {
    // Fetch provider metadata
    let issuer_url = IssuerUrl::new("https://accounts.google.com".to_string())?;
    let provider_metadata = CoreProviderMetadata::discover_async(
        issuer_url,
        oidc_async_http_client
    ).await?;
    
    // Create client with full metadata
    let client_id = OidcClientId::new(settings.client_id.clone());
    let client_secret = OidcClientSecret::new(settings.client_secret.expose_secret().clone());
    let redirect_url = OidcRedirectUrl::new(settings.redirect_uri.clone())?;
    
    let client = CoreClient::from_provider_metadata(
        provider_metadata,
        client_id,
        Some(client_secret)
    )
    .set_redirect_uri(redirect_url);
    
    Ok(client)
}
```

## Authorization URL Generation
```rust
/// Generate OIDC authorization URL
pub async fn generate_oidc_auth_url(
    client: &CoreClient,
    scopes: &[String],
) -> (Url, CsrfToken, PkceCodeVerifier, Nonce) {
    // Generate security parameters
    let (pkce_challenge, pkce_verifier) = PkceCodeChallenge::new_random_sha256();
    let state = CsrfToken::new_random();
    let nonce = Nonce::new_random();
    
    // Build authorization URL with all required parameters
    let mut auth_url = client
        .authorize_url(
            AuthenticationFlow::<CoreResponseType>::AuthorizationCode,
            || state.clone(),
            || nonce.clone()
        )
        .set_pkce_challenge(pkce_challenge);
    
    // Add all requested scopes
    for scope in scopes {
        auth_url = auth_url.add_scope(Scope::new(scope.clone()));
    }
    
    (auth_url.url(), state, pkce_verifier, nonce)
}
```

## Token Exchange with Verification
```rust
/// Exchange authorization code for tokens
pub async fn exchange_oidc_code(
    client: &CoreClient,
    code: &str,
    pkce_verifier: PkceCodeVerifier,
    nonce: &Nonce,
) -> AppResult<(CoreTokenResponse, CoreIdTokenClaims)> {
    // Exchange code for tokens
    let token_response = client
        .exchange_code(AuthorizationCode::new(code.to_string()))
        .set_pkce_verifier(pkce_verifier)
        .request_async(oidc_async_http_client)
        .await?;
    
    // Verify ID token
    let id_token = token_response
        .id_token()
        .ok_or_else(|| AppError::InvalidToken("Missing ID token".to_string()))?;
    
    let claims = id_token
        .claims(&client.id_token_verifier(), nonce)
        .map_err(|e| AppError::InvalidToken(format!("Invalid ID token: {}", e)))?;
    
    Ok((token_response, claims.clone()))
}
```

## User Info Retrieval
```rust
/// Fetch user info from OIDC provider
pub async fn fetch_user_info(
    client: &CoreClient,
    access_token: &AccessToken,
) -> AppResult<CoreUserInfoClaims> {
    // Get provider metadata to check for userinfo endpoint
    let metadata = client
        .provider_metadata()
        .ok_or_else(|| AppError::OAuthUserInfoFailed("Missing provider metadata".to_string()))?;
    
    // Verify userinfo endpoint is available
    let userinfo_url = metadata
        .userinfo_endpoint()
        .ok_or_else(|| AppError::OAuthUserInfoFailed("Provider missing userinfo endpoint".to_string()))?;
    
    // Create client with userinfo URL
    let userinfo_client = client
        .clone()
        .set_user_info_url(userinfo_url.clone());
    
    // Request user info
    let user_info = userinfo_client
        .user_info(access_token.clone(), None)
        .request_async(oidc_async_http_client)
        .await?;
    
    Ok(user_info)
}
```

</patterns>

<examples>

## Complete OIDC Authentication Flow
```rust
/// Handle OpenID Connect authentication flow
pub async fn authenticate_with_oidc(
    &self,
    provider: &str,
    code: &str,
    state: &str,
    stored_state: &str,
    stored_pkce_verifier: PkceCodeVerifier,
    stored_nonce: Nonce,
) -> AppResult<User> {
    // Verify state parameter to prevent CSRF
    if state != stored_state {
        return Err(AppError::InvalidToken("State mismatch, possible CSRF attack".to_string()));
    }
    
    // Create OIDC client
    let client = self.create_oidc_client(provider).await?;
    
    // Exchange code for tokens and verify ID token
    let (token_response, id_claims) = exchange_oidc_code(
        &client, 
        code, 
        stored_pkce_verifier, 
        &stored_nonce
    ).await?;
    
    // Extract identity information from ID token
    let sub = id_claims.subject().to_string();
    let email = id_claims
        .email()
        .map(|e| e.to_string())
        .ok_or_else(|| AppError::OAuthUserInfoFailed("Email missing from ID token".to_string()))?;
    
    // Fetch additional user information if needed
    let user_info = fetch_user_info(&client, token_response.access_token()).await?;
    
    // Get or create user in our system
    let user = self.user_service
        .find_or_create_oauth_user(provider, &sub, &email, user_info.name().map(|n| n.to_string()))
        .await?;
    
    // Create session for the user
    let session = self.session_service
        .create_session(user.id, Some(provider.to_string()))
        .await?;
    
    // Return authenticated user
    Ok(user)
}
```

## Custom Claim Extraction
```rust
/// Extract custom claims from OIDC ID token
pub fn extract_custom_claims(
    claims: &CoreIdTokenClaims,
) -> AppResult<UserProfile> {
    // Extract standard claims
    let sub = claims.subject().to_string();
    let email = claims
        .email()
        .map(|e| e.to_string())
        .ok_or_else(|| AppError::OAuthUserInfoFailed("Email missing from ID token".to_string()))?;
    let name = claims.name().map(|n| n.to_string());
    
    // Extract additional claims if available
    let picture = claims
        .additional_claims()
        .picture
        .as_ref()
        .map(|p| p.to_string());
    
    let locale = claims
        .additional_claims()
        .locale
        .as_ref()
        .map(|l| l.to_string());
    
    // Create user profile
    Ok(UserProfile {
        provider_user_id: sub,
        email,
        name,
        picture,
        locale,
        email_verified: claims.email_verified().unwrap_or(false),
    })
}
```

</examples>

<troubleshooting>

## Common Errors

### Method Not Found Errors
- "no method named `exchange_code` found for struct `CoreClient<...>`"
  - Cause: Client not properly configured with token endpoint
  - Solution: Create client using `from_provider_metadata` to ensure all endpoints are configured

- "no method named `provider_metadata` found for reference `&CoreClient<...>`"
  - Cause: Using a client not created from provider metadata
  - Solution: Create client using `CoreClient::from_provider_metadata()`

- "no method named `authorize_url` found for struct `CoreClient<...>`"
  - Cause: Client not properly configured with authorization endpoint
  - Solution: Create client using provider metadata discovery

### Method Name Confusion
- "no method named `userinfo` found"
  - Cause: Incorrect method name
  - Solution: Use `user_info()` (with underscore) instead of `userinfo()`

- "no method named `set_userinfo_url` found"
  - Cause: Incorrect method name
  - Solution: Use `set_user_info_url()` (with underscore) instead of `set_userinfo_url()`

### Endpoint Type Errors
- "expected struct with `EndpointNotSet`, found struct with `EndpointSet`"
  - Cause: Type mismatch due to client configuration state
  - Solution: Ensure return types match the actual configuration state of the client

### Parameter Errors
- "arguments to this enum variant are incorrect"
  - Cause: Incorrect parameters to method calls
  - Solution: Check parameter types and ensure closures are used where needed (e.g., `|| state.clone()`)

## Debugging Tips
- Enable detailed logging for OIDC/OAuth2 operations
- Log provider metadata to ensure all required endpoints are available
- Use debug assertions to verify token properties before use
- Implement thorough error handling with clear error messages

</troubleshooting>
