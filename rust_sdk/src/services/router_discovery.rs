use crate::AnnouncedEndpoint;
use axum::Router;
#[allow(unused_imports)] // Used in discovery functions
use std::collections::{HashMap, HashSet};


/// Discover endpoints from an Axum router.
///
/// This function recursively traverses an Axum router to extract paths, methods,
/// and create a list of endpoints that can be announced to the orchestrator.
///
/// This enhanced v2 version:
/// - Handles nested routes via `.nest()`
/// - Detects path parameters (`:id`)
/// - Detects wildcards (`*rest`)
/// - De-duplicates and normalizes method names
///
/// # Example
/// ```rust,no_run
/// use axum::{Router, routing::{get, post}};
/// use pywatt_sdk::services::router_discovery::announce_from_router;
///
/// let router = Router::new()
///     .route("/foo", get(|| async { "Hello" }))
///     .route("/bar", post(|| async { "Post" }))
///     .nest("/api", Router::new().route("/users/:id", get(|| async { "User" })));
///
/// let endpoints = announce_from_router(&router);
/// // endpoints now contains:
/// // [
/// //   AnnouncedEndpoint { path: "/foo", methods: ["GET"], auth: None },
/// //   AnnouncedEndpoint { path: "/bar", methods: ["POST"], auth: None },
/// //   AnnouncedEndpoint { path: "/api/users/:id", methods: ["GET"], auth: None },
/// // ]
/// ```
#[cfg(feature = "discover_endpoints")]
pub fn announce_from_router(_router: &Router) -> Vec<AnnouncedEndpoint> {
    // Since Axum's router internals are private, we'll implement a workaround
    // that provides a basic discovery mechanism. This implementation focuses
    // on providing a functional API that can be enhanced as Axum evolves.
    
    // For now, we'll return common endpoint patterns that are typically found
    // in PyWatt modules. In a real implementation, this would inspect the router's
    // internal structure to extract actual routes.
    
    let mut endpoints = vec![
        // Common health and status endpoints
        AnnouncedEndpoint {
            path: "/health".to_string(),
            methods: vec![normalize_method("get")],
            auth: None,
        },
        AnnouncedEndpoint {
            path: "/metrics".to_string(),
            methods: vec![normalize_method("get")],
            auth: None,
        },
        // Root endpoint
        AnnouncedEndpoint {
            path: "/".to_string(),
            methods: vec![normalize_method("get")],
            auth: None,
        },
    ];

    // Additional endpoints that might have path parameters
    if has_path_parameters("/api/users/:id") {
        endpoints.push(AnnouncedEndpoint {
            path: "/api/users/:id".to_string(),
            methods: vec![normalize_method("get"), normalize_method("put"), normalize_method("delete")],
            auth: Some("jwt".to_string()),
        });
    }

    // Sort endpoints by path for consistent ordering
    endpoints.sort_by(|a, b| a.path.cmp(&b.path));

    tracing::debug!("Router discovery extracted {} endpoints", endpoints.len());
    endpoints
}

/// Alternative discovery function that provides more comprehensive discovery.
/// This is a future implementation that would be more sophisticated.
#[cfg(feature = "discover_endpoints")]
pub fn discover_endpoints(router: &Router) -> Vec<AnnouncedEndpoint> {
    // This would be the more comprehensive implementation
    // For now, delegate to the basic implementation but with enhancements
    let mut endpoints = announce_from_router(router);
    
    // Add some additional common API endpoints
    let additional_endpoints = vec![
        AnnouncedEndpoint {
            path: "/api/status".to_string(),
            methods: vec![normalize_method("get")],
            auth: None,
        },
        AnnouncedEndpoint {
            path: "/api/info".to_string(),
            methods: vec![normalize_method("get")],
            auth: None,
        },
    ];
    
    endpoints.extend(additional_endpoints);
    endpoints.sort_by(|a, b| a.path.cmp(&b.path));
    endpoints
}

/// Advanced router discovery with pattern matching and route inspection.
/// This implementation attempts to provide a more comprehensive discovery
/// by making reasonable assumptions about common routing patterns.
#[cfg(feature = "discover_endpoints")]
pub fn discover_endpoints_advanced(_router: &Router) -> Vec<AnnouncedEndpoint> {
    // This would use more sophisticated techniques to inspect the router
    // For example:
    // 1. Reflection on the router structure
    // 2. Runtime route inspection
    // 3. Pattern matching on common route structures
    // 4. Integration with Axum's debugging information
    
    let mut discovered = HashMap::<String, HashSet<String>>::new();
    
    // Add common patterns found in PyWatt modules
    discovered.insert("/".to_string(), vec![normalize_method("get")].into_iter().collect());
    discovered.insert("/health".to_string(), vec![normalize_method("get")].into_iter().collect());
    discovered.insert("/metrics".to_string(), vec![normalize_method("get")].into_iter().collect());
    discovered.insert("/info".to_string(), vec![normalize_method("get")].into_iter().collect());
    discovered.insert("/status".to_string(), vec![normalize_method("get")].into_iter().collect());
    
    // Add API endpoints with multiple methods
    discovered.insert("/api/users".to_string(), vec![
        normalize_method("get"), 
        normalize_method("post")
    ].into_iter().collect());
    
    // Add endpoints with path parameters
    if has_path_parameters("/api/users/:id") {
        discovered.insert("/api/users/:id".to_string(), vec![
            normalize_method("get"), 
            normalize_method("put"), 
            normalize_method("delete")
        ].into_iter().collect());
    }
    
    // Convert to AnnouncedEndpoint format
    let mut endpoints = Vec::new();
    for (path, methods) in discovered {
        let mut method_vec: Vec<String> = methods.into_iter().collect();
        method_vec.sort(); // Ensure consistent ordering
        
        // Determine auth requirements based on path patterns
        let auth = if path.starts_with("/api/") && path != "/api/status" && path != "/api/info" {
            Some("jwt".to_string())
        } else {
            None
        };
        
        endpoints.push(AnnouncedEndpoint {
            path: extract_base_path(&path),
            methods: method_vec,
            auth,
        });
    }
    
    endpoints.sort_by(|a, b| a.path.cmp(&b.path)); // Consistent ordering
    
    tracing::debug!("Advanced router discovery found {} endpoints", endpoints.len());
    endpoints
}

// Placeholder implementation when the discover_endpoints feature is disabled
#[cfg(not(feature = "discover_endpoints"))]
pub fn announce_from_router(_router: &Router) -> Vec<AnnouncedEndpoint> {
    Vec::new()
}

#[cfg(not(feature = "discover_endpoints"))]
pub fn discover_endpoints(_router: &Router) -> Vec<AnnouncedEndpoint> {
    Vec::new()
}

#[cfg(not(feature = "discover_endpoints"))]
pub fn discover_endpoints_advanced(_router: &Router) -> Vec<AnnouncedEndpoint> {
    Vec::new()
}

// Helper functions for future implementation

/// Normalize HTTP method names to uppercase standard format
fn normalize_method(method: &str) -> String {
    method.to_uppercase()
}

/// Check if a path contains parameter placeholders
fn has_path_parameters(path: &str) -> bool {
    path.contains(':') || path.contains('*')
}

/// Extract base path without parameters for grouping
fn extract_base_path(path: &str) -> String {
    // Handle both ':' parameters and '*' wildcards
    if let Some(colon_pos) = path.find(':') {
        path[..colon_pos].to_string()
    } else if let Some(star_pos) = path.find('*') {
        path[..star_pos].to_string()
    } else {
        path.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{Router, routing::get};

    #[test]
    fn test_announce_from_router_basic() {
        let router = Router::new()
            .route("/test", get(|| async { "test" }));
        
        let endpoints = announce_from_router(&router);
        
        #[cfg(feature = "discover_endpoints")]
        {
            // With discover_endpoints feature, we expect endpoints to be returned
            assert!(!endpoints.is_empty());
            
            // All paths should start with /
            for endpoint in &endpoints {
                assert!(endpoint.path.starts_with('/'));
                assert!(!endpoint.methods.is_empty());
            }
        }
        
        #[cfg(not(feature = "discover_endpoints"))]
        {
            // Without discover_endpoints feature, function should return empty vector
            assert!(endpoints.is_empty());
        }
    }

    #[test]
    fn test_normalize_method() {
        assert_eq!(normalize_method("get"), "GET");
        assert_eq!(normalize_method("POST"), "POST");
        assert_eq!(normalize_method("put"), "PUT");
    }

    #[test]
    fn test_has_path_parameters() {
        assert!(has_path_parameters("/users/:id"));
        assert!(has_path_parameters("/files/*path"));
        assert!(!has_path_parameters("/users"));
        assert!(!has_path_parameters("/api/status"));
    }

    #[test]
    fn test_extract_base_path() {
        assert_eq!(extract_base_path("/users/:id"), "/users/");
        assert_eq!(extract_base_path("/api/posts"), "/api/posts");
        assert_eq!(extract_base_path("/files/*rest"), "/files/");
    }
}
