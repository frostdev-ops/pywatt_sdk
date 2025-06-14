use crate::OrchestratorInit;
use crate::ipc_types::ListenAddress;
use std::net::SocketAddr;
use std::path::PathBuf;

#[cfg(feature = "router_ext")]
use axum::Router;
#[cfg(feature = "router_ext")]
use serde_json::json;

/// Extension methods for working with OrchestratorInit.
pub trait OrchestratorInitExt {
    /// Convert the listen address into a string representation (TCP or UDS path).
    fn listen_to_string(&self) -> String;
    /// Get the raw ListenAddress enum reference.
    #[allow(dead_code)] // Potentially useful for consumers, keep despite warning
    fn listen_address(&self) -> &ListenAddress;
    /// Get the TCP channel address if available
    fn tcp_address(&self) -> Option<SocketAddr>;
    /// Get the TCP channel address as a string if available
    fn tcp_address_string(&self) -> Option<String>;
    /// Check if TLS is enabled for the TCP channel
    fn tcp_tls_enabled(&self) -> bool;
    /// Get the IPC socket path if available
    fn ipc_socket_path(&self) -> Option<PathBuf>;
    /// Check if IPC channel is available
    fn has_ipc_channel(&self) -> bool;
    /// Check if TCP channel is available
    fn has_tcp_channel(&self) -> bool;
    /// Get a human-readable summary of available channels
    fn channel_summary(&self) -> String;
}

impl OrchestratorInitExt for OrchestratorInit {
    fn listen_to_string(&self) -> String {
        match &self.listen {
            ListenAddress::Tcp(addr) => addr.to_string(),
            ListenAddress::Unix(path) => path.to_string_lossy().to_string(),
        }
    }

    fn listen_address(&self) -> &ListenAddress {
        &self.listen
    }

    fn tcp_address(&self) -> Option<SocketAddr> {
        self.tcp_channel.as_ref().map(|config| config.address)
    }

    fn tcp_address_string(&self) -> Option<String> {
        self.tcp_address().map(|addr| addr.to_string())
    }

    fn tcp_tls_enabled(&self) -> bool {
        self.tcp_channel.as_ref().is_some_and(|config| config.tls_enabled)
    }

    fn ipc_socket_path(&self) -> Option<PathBuf> {
        self.ipc_channel.as_ref().map(|config| config.socket_path.clone())
    }

    fn has_ipc_channel(&self) -> bool {
        self.ipc_channel.is_some()
    }

    fn has_tcp_channel(&self) -> bool {
        self.tcp_channel.is_some()
    }

    fn channel_summary(&self) -> String {
        let mut channels = Vec::new();
        
        if let Some(tcp_addr) = self.tcp_address_string() {
            let tls_status = if self.tcp_tls_enabled() { " (TLS)" } else { "" };
            channels.push(format!("TCP:{}{}", tcp_addr, tls_status));
        }
        
        if let Some(ipc_path) = self.ipc_socket_path() {
            channels.push(format!("IPC:{}", ipc_path.display()));
        }
        
        if channels.is_empty() {
            "No communication channels configured".to_string()
        } else {
            channels.join(", ")
        }
    }
}

/// Extension methods for the ListenAddress enum.
pub trait ListenExt {
    /// Convert the ListenAddress into a string representation.
    #[allow(dead_code)] // Potentially useful for consumers, keep despite warning
    fn to_string_lossy(&self) -> String;
}

impl ListenExt for ListenAddress {
    fn to_string_lossy(&self) -> String {
        match self {
            ListenAddress::Tcp(addr) => addr.to_string(),
            ListenAddress::Unix(path) => path.to_string_lossy().to_string(),
        }
    }
}

/// Extension methods for adding common endpoints to a Router.
///
/// These methods add standard health and metrics endpoints to your router.
#[cfg(feature = "router_ext")]
pub trait RouterExt {
    /// Add a default health endpoint returning 200 OK with build info.
    ///
    /// # Example
    /// ```rust,no_run
    /// # #[cfg(feature = "router_ext")]
    /// # fn main() {
    /// # use axum::Router;
    /// use pywatt_sdk::ext::RouterExt; // import from crate root
    ///
    /// let router: Router<()> = Router::new().with_default_health();
    /// # }
    /// # #[cfg(not(feature = "router_ext"))]
    /// # fn main() {}
    /// ```
    fn with_default_health(self) -> Self;

    /// Add a CORS preflight handler for all routes.
    ///
    /// This method is only available with the `cors` feature.
    ///
    /// # Example
    /// ```rust,no_run
    /// # #[cfg(all(feature = "router_ext", feature = "cors"))]
    /// # fn main() {
    /// # use axum::Router;
    /// use pywatt_sdk::ext::RouterExt; // import from crate root
    ///
    /// let router: Router<()> = Router::new().with_cors_preflight();
    /// # }
    /// # #[cfg(not(all(feature = "router_ext", feature = "cors")))]
    /// # fn main() {}
    /// ```
    #[cfg(feature = "cors")]
    fn with_cors_preflight(self) -> Self;

    /// Add a Prometheus metrics endpoint at `/metrics`.
    ///
    /// This method is only available with the `metrics` feature.
    ///
    /// # Example
    /// ```rust,no_run
    /// # #[cfg(all(feature = "router_ext", feature = "metrics"))]
    /// # fn main() {
    /// # use axum::Router;
    /// use pywatt_sdk::ext::RouterExt; // import from crate root
    ///
    /// let router: Router<()> = Router::new().with_prometheus_metrics();
    /// # }
    /// # #[cfg(not(all(feature = "router_ext", feature = "metrics")))]
    /// # fn main() {}
    /// ```
    #[cfg(feature = "metrics")]
    fn with_prometheus_metrics(self) -> Self;
}

#[cfg(feature = "router_ext")]
impl<S> RouterExt for Router<S>
where
    S: Clone + Send + Sync + 'static,
{
    fn with_default_health(self) -> Self {
        use axum::routing::get;

        self.route(
            "/health",
            get(|| async {
                let build_info = json!({
                    "git": crate::build::GIT_HASH,
                    "time": crate::build::BUILD_TIME_UTC,
                    "rustc": crate::build::RUSTC_VERSION,
                    "status": "OK"
                });

                axum::Json(build_info)
            }),
        )
    }

    #[cfg(feature = "cors")]
    fn with_cors_preflight(self) -> Self {
        use axum::http::{HeaderValue, header};
        use axum::response::IntoResponse;
        use std::convert::Infallible;
        use http::Request;

        // CORS preflight handler
        async fn handle_cors_preflight(
            req: axum::http::Request<axum::body::Body>,
        ) -> axum::response::Response {
            let headers = req.headers();
            let origin = headers
                .get(header::ORIGIN)
                .cloned()
                .unwrap_or_else(|| HeaderValue::from_static("*"));

            let requested_method = headers
                .get(header::ACCESS_CONTROL_REQUEST_METHOD)
                .cloned()
                .unwrap_or_else(|| HeaderValue::from_static("GET, POST, PUT, DELETE, OPTIONS"));

            let requested_headers = headers
                .get(header::ACCESS_CONTROL_REQUEST_HEADERS)
                .cloned()
                .unwrap_or_else(|| HeaderValue::from_static("*"));

            axum::response::Response::builder()
                .status(axum::http::StatusCode::NO_CONTENT)
                .header(header::ACCESS_CONTROL_ALLOW_ORIGIN, origin)
                .header(header::ACCESS_CONTROL_ALLOW_METHODS, requested_method)
                .header(header::ACCESS_CONTROL_ALLOW_HEADERS, requested_headers)
                .header(header::ACCESS_CONTROL_MAX_AGE, "86400")
                .body(axum::body::Body::empty())
                .unwrap()
                .into_response()
        }

        // Add CORS headers middleware
        let cors_layer = tower::ServiceBuilder::new().layer(axum::middleware::from_fn(
            move |req: Request<axum::body::Body>, next: axum::middleware::Next| async move {
                let response = next.run(req).await;

                // Add CORS headers to all responses
                let mut modified_response = response.into_response();
                let headers = modified_response.headers_mut();
                headers.insert(
                    header::ACCESS_CONTROL_ALLOW_ORIGIN,
                    HeaderValue::from_static("*"),
                );
                headers.insert(
                    header::ACCESS_CONTROL_ALLOW_METHODS,
                    HeaderValue::from_static("GET, POST, PUT, DELETE, OPTIONS"),
                );
                headers.insert(
                    header::ACCESS_CONTROL_ALLOW_HEADERS,
                    HeaderValue::from_static("Content-Type, Authorization"),
                );

                Ok::<_, Infallible>(modified_response)
            },
        ));

        // Create options handler for all paths
        let options_handler = axum::routing::MethodRouter::new().options(handle_cors_preflight);

        // Use the handler directly as the fallback
        self.layer(cors_layer).fallback(options_handler)
    }

    #[cfg(feature = "metrics")]
    fn with_prometheus_metrics(self) -> Self {
        use axum::http::StatusCode;
        use axum::response::IntoResponse;
        use axum::routing::get;
        use prometheus::{Encoder, TextEncoder, gather};

        async fn metrics_handler() -> impl IntoResponse {
            let encoder = TextEncoder::new();
            let metric_families = gather();
            let mut buffer = Vec::new();
            
            if let Err(e) = encoder.encode(&metric_families, &mut buffer) {
                return (
                    StatusCode::INTERNAL_SERVER_ERROR, 
                    format!("metrics encoding error: {}", e)
                );
            }
            
            (StatusCode::OK, String::from_utf8_lossy(&buffer).to_string())
        }

        self.route("/metrics", get(metrics_handler))
    }
}

// Re-export when jwt_auth feature is enabled (may be unused in some builds)
#[cfg(feature = "jwt_auth")]
#[allow(unused_imports)]
pub use crate::jwt_auth::{JwtAuthLayer, RouterJwtExt};
