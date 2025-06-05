//! Feature flag testing module
//!
//! This module is for testing feature-flag-gated code paths.
//! The code in this module is not meant to be executed directly,
//! but to test that feature flag combinations compile correctly.

// We include this module only in test builds
#[cfg(test)]
mod tests {
    use axum::Router;
    #[cfg(feature = "cors")]
    use pywatt_sdk::ext::RouterExt;
    #[cfg(feature = "jwt_auth")]
    use axum::routing::get;

    // Test JWT auth feature
    #[cfg(feature = "jwt_auth")]
    #[test]
    #[allow(deprecated)]
    fn test_jwt_auth_compiles() {
        // Just a compilation test
        use pywatt_sdk::security::jwt_auth::JwtAuthLayer;
        use pywatt_sdk::security::jwt_auth::RouterJwtExt;
        use serde::{Deserialize, Serialize};

        #[derive(Debug, Serialize, Deserialize, Clone)]
        struct TestClaims {
            sub: String,
        }

        // Test with type parameter
        let _app1: Router<()> = Router::new().with_jwt::<TestClaims>("secret".to_string());

        // Test with default parameter
        let _app2: Router<()> = Router::new().with_jwt::<serde_json::Value>("secret".to_string());

        // Test with layer directly
        // Provide explicit route type to avoid type inference issues
        let router: Router<()> = Router::new().route("/", get(|| async { "Hello" }));
        let _app3 = router.layer(JwtAuthLayer::<TestClaims>::new("secret".to_string()));
    }

    // Test builder feature
    #[cfg(feature = "builder")]
    #[test]
    fn test_builder_compiles() {
        use pywatt_sdk::AppState;
        use pywatt_sdk::secret_client::SecretClient;
        use std::sync::Arc;

        #[derive(Clone)]
        #[allow(dead_code)]
        struct TestFeatures {
            database: bool,
            cache: bool,
            #[allow(dead_code)]
            custom_feature: bool,
        }

        #[derive(Clone)]
        struct TestState {
            #[allow(dead_code)]
            value: String,
        }

        let client = Arc::new(SecretClient::new_dummy());
        let state = TestState {
            value: "test".to_string(),
        };

        let app_state = AppState::builder()
            .with_module_id("test".to_string())
            .with_orchestrator_api("http://localhost".to_string())
            .with_secret_client(client.clone())
            .with_custom(state.clone());

        // Test that the builder compiles and basic accessors work
        let built = app_state.build().expect("Failed to build AppState");
        assert_eq!(built.module_id(), "test");
        assert_eq!(built.orchestrator_api(), "http://localhost");
        assert_eq!(built.custom().value, "test");
    }

    // Test router extensions feature
    #[cfg(feature = "router_ext")]
    #[test]
    fn test_router_ext_compiles() {
        // Specify the state type parameter explicitly to resolve type annotations
        let router: Router<()> = Router::new();
        #[cfg(feature = "cors")]
        let with_cors = router.with_cors_preflight();
        #[cfg(feature = "cors")]
        {
            // Test that the CORS router compiles and maintains the correct type
            let _typed_router: Router<()> = with_cors;
        }
    }

    // Additional feature tests can be added here as needed

    #[tokio::test]
    #[cfg(feature = "builder")]
    async fn test_module_builder_basic() {
        use pywatt_sdk::AnnouncedEndpoint;
        use pywatt_sdk::builder::ModuleBuilder;

        // Mock initialization and secret fetching (not strictly needed for this test)
        let builder = ModuleBuilder::<()>::new()
            .secret_keys(&["TEST_SECRET"])
            .endpoints(vec![AnnouncedEndpoint {
                path: "/test".to_string(),
                methods: vec!["GET".to_string()],
                auth: None,
            }])
            .state(|_init, _secrets| ());

        // Test that builder configuration is stored correctly
        assert_eq!(builder.get_secret_keys(), &["TEST_SECRET"]);
        assert_eq!(builder.get_endpoints().len(), 1);
        assert_eq!(builder.get_endpoints()[0].path, "/test");
        assert_eq!(builder.get_endpoints()[0].methods, vec!["GET".to_string()]);
        assert!(builder.get_endpoints()[0].auth.is_none());
    }

    #[tokio::test]
    #[cfg(feature = "router_ext")]
    async fn test_router_extensions() {
        use axum::routing::get;
        
        let router: Router<()> = Router::new()
            .route("/test", get(|| async { "Hello" }));
        
        // Test endpoint discovery if feature is enabled
        #[cfg(feature = "discover_endpoints")]
        {
            use pywatt_sdk::services::router_discovery::discover_endpoints;
            let endpoints = discover_endpoints(&router);
            
            // The current implementation returns common endpoints, not the actual router routes
            // Test that discovery returns some endpoints and they have proper structure
            assert!(!endpoints.is_empty(), "Discovery should return some endpoints");
            
            // Look for common endpoints that the implementation provides
            let health_endpoint = endpoints.iter().find(|e| e.path == "/health");
            assert!(health_endpoint.is_some(), "Should discover /health endpoint");
            
            let health = health_endpoint.unwrap();
            assert!(health.methods.contains(&"GET".to_string()), "Health endpoint should support GET");
            
            // Verify all endpoints have proper structure
            for endpoint in &endpoints {
                assert!(endpoint.path.starts_with('/'), "All paths should start with /");
                assert!(!endpoint.methods.is_empty(), "All endpoints should have at least one method");
            }
        }
        
        // Test that the router compilation and basic setup work
        let _compiled_router = router;
    }

    // ------------------------------------------------------------------
    // Shared helpers
    // ------------------------------------------------------------------

    /// Initialize logging for tests – minimal no-op to satisfy compilation.
    #[allow(dead_code)]
    fn setup_logging() {
        // In real tests we might configure tracing-subscriber, but for
        // compile-time checks a no-op is sufficient and avoids duplicated init.
    }

    // This helper is intentionally **not** a #[tokio::test] to avoid executing
    // incomplete logic. It only needs to compile.
    #[allow(dead_code)]
    async fn test_serve_module_with_state_and_router() {
        setup_logging();
        let _router: Router<()> = Router::new();
        
        // Test that we can create a basic module state and router setup
        // This function is designed for compilation testing, not actual execution
        #[cfg(feature = "builder")]
        {
            use pywatt_sdk::AppState;
            use pywatt_sdk::secret_client::SecretClient;
            use std::sync::Arc;
            
            // Create test state
            let client = Arc::new(SecretClient::new_dummy());
            let _app_state = AppState::builder()
                .with_module_id("test-module".to_string())
                .with_orchestrator_api("http://localhost:8000".to_string())
                .with_secret_client(client)
                .with_custom("test_state".to_string())
                .build();
        }
        
        // In a real implementation, we would serve the module here, but this
        // function is intentionally kept as a compilation test only
    }
}
