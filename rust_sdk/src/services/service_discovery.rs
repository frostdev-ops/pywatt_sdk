//! Service discovery functionality for PyWatt modules.
//!
//! This module provides functionality for modules to register as service providers
//! and discover other services in the PyWatt ecosystem.

use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::Mutex;
use tracing::{debug, error, info, warn};
use uuid::Uuid;

use crate::communication::ipc_types::{
    ServiceType, RegisterServiceProviderRequest, RegisterServiceProviderResponse,
    DiscoverServiceProvidersRequest, DiscoverServiceProvidersResponse,
    ServiceProviderInfo, ModuleToOrchestrator, OrchestratorToModule,
};
use crate::message::{Message, MessageMetadata, EncodingFormat};
use crate::communication::{MessageChannel, TcpChannel};
use crate::communication::tcp_types::ConnectionConfig;

/// Result type for service discovery operations.
pub type Result<T> = std::result::Result<T, ServiceDiscoveryError>;

/// Errors that can occur during service discovery operations.
#[derive(Debug, thiserror::Error)]
pub enum ServiceDiscoveryError {
    #[error("Connection error: {0}")]
    ConnectionError(String),
    
    #[error("Serialization error: {0}")]
    SerializationError(String),
    
    #[error("Channel error: {0}")]
    ChannelError(String),
    
    #[error("Timeout error")]
    Timeout,
    
    #[error("Registration failed: {0}")]
    RegistrationFailed(String),
    
    #[error("Discovery failed: {0}")]
    DiscoveryFailed(String),
}

/// Service discovery client for PyWatt modules.
pub struct ServiceDiscoveryClient {
    /// Connection to the orchestrator
    channel: Arc<TcpChannel>,
    /// Registered service providers for this module
    registered_providers: Arc<Mutex<HashMap<String, RegisteredProvider>>>,
}

/// Information about a registered service provider.
#[derive(Debug, Clone)]
pub struct RegisteredProvider {
    pub provider_id: String,
    pub service_type: ServiceType,
    pub name: String,
    pub version: Option<String>,
    pub address: String,
    pub metadata: HashMap<String, String>,
}

impl ServiceDiscoveryClient {
    /// Create a new service discovery client.
    ///
    /// # Arguments
    /// * `config` - Connection configuration for the orchestrator
    ///
    /// # Returns
    /// A new service discovery client
    pub async fn new(config: ConnectionConfig) -> Result<Self> {
        let channel = TcpChannel::connect(config).await
            .map_err(|e| ServiceDiscoveryError::ConnectionError(e.to_string()))?;
        
        Ok(Self {
            channel: Arc::new(channel),
            registered_providers: Arc::new(Mutex::new(HashMap::new())),
        })
    }

    /// Register this module as a service provider.
    ///
    /// # Arguments
    /// * `service_type` - Type of service being provided
    /// * `name` - Human-readable name for the service
    /// * `address` - Network address where the service can be reached
    ///
    /// # Returns
    /// The provider ID if successful
    pub async fn register_service_provider(
        &self,
        service_type: ServiceType,
        name: impl Into<String>,
        address: impl Into<String>,
    ) -> Result<String> {
        let name = name.into();
        let address = address.into();
        
        let request = RegisterServiceProviderRequest {
            service_type: service_type.clone(),
            name: name.clone(),
            version: None,
            address: address.clone(),
            metadata: None,
        };

        let message = ModuleToOrchestrator::RegisterServiceProvider(request);
        let response = self.send_request(message).await?;

        match response {
            OrchestratorToModule::RegisterServiceProviderResponse(resp) => {
                if resp.success {
                    if let Some(provider_id) = resp.provider_id {
                        // Store the registered provider
                        let provider = RegisteredProvider {
                            provider_id: provider_id.clone(),
                            service_type,
                            name,
                            version: None,
                            address,
                            metadata: HashMap::new(),
                        };
                        
                        let mut providers = self.registered_providers.lock().await;
                        providers.insert(provider_id.clone(), provider);
                        
                        info!("Successfully registered as service provider: {}", provider_id);
                        Ok(provider_id)
                    } else {
                        Err(ServiceDiscoveryError::RegistrationFailed("No provider ID returned".to_string()))
                    }
                } else {
                    let error = resp.error.unwrap_or_else(|| "Unknown error".to_string());
                    Err(ServiceDiscoveryError::RegistrationFailed(error))
                }
            }
            _ => Err(ServiceDiscoveryError::RegistrationFailed("Unexpected response type".to_string())),
        }
    }

    /// Register this module as a service provider with additional options.
    ///
    /// # Arguments
    /// * `service_type` - Type of service being provided
    /// * `name` - Human-readable name for the service
    /// * `address` - Network address where the service can be reached
    /// * `version` - Optional version of the service
    /// * `metadata` - Optional metadata about the service
    ///
    /// # Returns
    /// The provider ID if successful
    pub async fn register_service_provider_with_options(
        &self,
        service_type: ServiceType,
        name: impl Into<String>,
        address: impl Into<String>,
        version: Option<String>,
        metadata: Option<HashMap<String, String>>,
    ) -> Result<String> {
        let name = name.into();
        let address = address.into();
        
        let request = RegisterServiceProviderRequest {
            service_type: service_type.clone(),
            name: name.clone(),
            version: version.clone(),
            address: address.clone(),
            metadata: metadata.clone(),
        };

        let message = ModuleToOrchestrator::RegisterServiceProvider(request);
        let response = self.send_request(message).await?;

        match response {
            OrchestratorToModule::RegisterServiceProviderResponse(resp) => {
                if resp.success {
                    if let Some(provider_id) = resp.provider_id {
                        // Store the registered provider
                        let provider = RegisteredProvider {
                            provider_id: provider_id.clone(),
                            service_type,
                            name,
                            version,
                            address,
                            metadata: metadata.unwrap_or_default(),
                        };
                        
                        let mut providers = self.registered_providers.lock().await;
                        providers.insert(provider_id.clone(), provider);
                        
                        info!("Successfully registered as service provider: {}", provider_id);
                        Ok(provider_id)
                    } else {
                        Err(ServiceDiscoveryError::RegistrationFailed("No provider ID returned".to_string()))
                    }
                } else {
                    let error = resp.error.unwrap_or_else(|| "Unknown error".to_string());
                    Err(ServiceDiscoveryError::RegistrationFailed(error))
                }
            }
            _ => Err(ServiceDiscoveryError::RegistrationFailed("Unexpected response type".to_string())),
        }
    }

    /// Discover service providers of a specific type.
    ///
    /// # Arguments
    /// * `service_type` - Type of service to discover
    /// * `all_providers` - Whether to return all providers or just the first healthy one
    ///
    /// # Returns
    /// A list of discovered service providers
    pub async fn discover_service_providers(
        &self,
        service_type: ServiceType,
        all_providers: bool,
    ) -> Result<Vec<ServiceProviderInfo>> {
        let request = DiscoverServiceProvidersRequest {
            service_type,
            all_providers: Some(all_providers),
        };

        let message = ModuleToOrchestrator::DiscoverServiceProviders(request);
        let response = self.send_request(message).await?;

        match response {
            OrchestratorToModule::DiscoverServiceProvidersResponse(resp) => {
                if resp.success {
                    debug!("Discovered {} service providers", resp.providers.len());
                    Ok(resp.providers)
                } else {
                    let error = resp.error.unwrap_or_else(|| "Unknown error".to_string());
                    Err(ServiceDiscoveryError::DiscoveryFailed(error))
                }
            }
            _ => Err(ServiceDiscoveryError::DiscoveryFailed("Unexpected response type".to_string())),
        }
    }

    /// Discover the first healthy service provider of a specific type.
    ///
    /// # Arguments
    /// * `service_type` - Type of service to discover
    ///
    /// # Returns
    /// The first healthy service provider, if any
    pub async fn discover_service_provider(
        &self,
        service_type: ServiceType,
    ) -> Result<Option<ServiceProviderInfo>> {
        let providers = self.discover_service_providers(service_type, false).await?;
        Ok(providers.into_iter().next())
    }

    /// Get all registered service providers for this module.
    ///
    /// # Returns
    /// A list of all registered service providers
    pub async fn get_registered_providers(&self) -> Vec<RegisteredProvider> {
        let providers = self.registered_providers.lock().await;
        providers.values().cloned().collect()
    }

    /// Send a request to the orchestrator and wait for a response.
    async fn send_request(&self, message: ModuleToOrchestrator) -> Result<OrchestratorToModule> {
        // Create message with request ID
        let mut metadata = MessageMetadata::new();
        metadata.id = Some(Uuid::new_v4().to_string());
        
        let msg = Message::with_metadata(message, metadata);
        let encoded = msg.encode()
            .map_err(|e| ServiceDiscoveryError::SerializationError(e.to_string()))?;
        
        // Send the request
        debug!("Sending service discovery request to orchestrator");
        self.channel.send(encoded).await
            .map_err(|e| ServiceDiscoveryError::ChannelError(e.to_string()))?;
        
        // Wait for response with timeout
        debug!("Waiting for service discovery response");
        let response_encoded = tokio::time::timeout(
            std::time::Duration::from_secs(30),
            self.channel.receive()
        ).await
        .map_err(|_| ServiceDiscoveryError::Timeout)?
        .map_err(|e| ServiceDiscoveryError::ChannelError(e.to_string()))?;
        
        // Decode response
        let response_data: OrchestratorToModule = serde_json::from_slice(response_encoded.data())
            .map_err(|e| ServiceDiscoveryError::SerializationError(e.to_string()))?;
        
        Ok(response_data)
    }
}

/// Builder for service provider registration.
pub struct ServiceProviderBuilder {
    service_type: ServiceType,
    name: String,
    address: String,
    version: Option<String>,
    metadata: HashMap<String, String>,
}

impl ServiceProviderBuilder {
    /// Create a new service provider builder.
    ///
    /// # Arguments
    /// * `service_type` - Type of service being provided
    /// * `name` - Human-readable name for the service
    /// * `address` - Network address where the service can be reached
    pub fn new(
        service_type: ServiceType,
        name: impl Into<String>,
        address: impl Into<String>,
    ) -> Self {
        Self {
            service_type,
            name: name.into(),
            address: address.into(),
            version: None,
            metadata: HashMap::new(),
        }
    }

    /// Set the version of the service.
    pub fn with_version(mut self, version: impl Into<String>) -> Self {
        self.version = Some(version.into());
        self
    }

    /// Add metadata to the service.
    pub fn with_metadata(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }

    /// Register the service provider using the given client.
    pub async fn register(self, client: &ServiceDiscoveryClient) -> Result<String> {
        client.register_service_provider_with_options(
            self.service_type,
            self.name,
            self.address,
            self.version,
            Some(self.metadata),
        ).await
    }
}

/// Convenience functions for common service types.
impl ServiceDiscoveryClient {
    /// Register as a database service provider.
    pub async fn register_database_provider(
        &self,
        name: impl Into<String>,
        address: impl Into<String>,
    ) -> Result<String> {
        self.register_service_provider(ServiceType::Database, name, address).await
    }

    /// Register as a cache service provider.
    pub async fn register_cache_provider(
        &self,
        name: impl Into<String>,
        address: impl Into<String>,
    ) -> Result<String> {
        self.register_service_provider(ServiceType::Cache, name, address).await
    }

    /// Register as a JWT service provider.
    pub async fn register_jwt_provider(
        &self,
        name: impl Into<String>,
        address: impl Into<String>,
    ) -> Result<String> {
        self.register_service_provider(ServiceType::Jwt, name, address).await
    }

    /// Register as a custom service provider.
    pub async fn register_custom_provider(
        &self,
        service_name: impl Into<String>,
        provider_name: impl Into<String>,
        address: impl Into<String>,
    ) -> Result<String> {
        let service_type = ServiceType::Custom(service_name.into());
        self.register_service_provider(service_type, provider_name, address).await
    }

    /// Discover database service providers.
    pub async fn discover_database_providers(&self, all: bool) -> Result<Vec<ServiceProviderInfo>> {
        self.discover_service_providers(ServiceType::Database, all).await
    }

    /// Discover cache service providers.
    pub async fn discover_cache_providers(&self, all: bool) -> Result<Vec<ServiceProviderInfo>> {
        self.discover_service_providers(ServiceType::Cache, all).await
    }

    /// Discover JWT service providers.
    pub async fn discover_jwt_providers(&self, all: bool) -> Result<Vec<ServiceProviderInfo>> {
        self.discover_service_providers(ServiceType::Jwt, all).await
    }

    /// Discover custom service providers.
    pub async fn discover_custom_providers(
        &self,
        service_name: impl Into<String>,
        all: bool,
    ) -> Result<Vec<ServiceProviderInfo>> {
        let service_type = ServiceType::Custom(service_name.into());
        self.discover_service_providers(service_type, all).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::SocketAddr;

    #[tokio::test]
    async fn test_service_provider_builder() {
        let builder = ServiceProviderBuilder::new(
            ServiceType::Database,
            "test-db",
            "localhost:5432",
        )
        .with_version("1.0.0")
        .with_metadata("driver", "postgresql")
        .with_metadata("max_connections", "100");

        assert_eq!(builder.service_type, ServiceType::Database);
        assert_eq!(builder.name, "test-db");
        assert_eq!(builder.address, "localhost:5432");
        assert_eq!(builder.version, Some("1.0.0".to_string()));
        assert_eq!(builder.metadata.get("driver"), Some(&"postgresql".to_string()));
        assert_eq!(builder.metadata.get("max_connections"), Some(&"100".to_string()));
    }

    #[test]
    fn test_service_type_display() {
        assert_eq!(ServiceType::Database.to_string(), "database");
        assert_eq!(ServiceType::Cache.to_string(), "cache");
        assert_eq!(ServiceType::Jwt.to_string(), "jwt");
        assert_eq!(ServiceType::Custom("my-service".to_string()).to_string(), "custom:my-service");
    }

    #[test]
    fn test_service_type_custom() {
        let custom_type = ServiceType::custom("my-custom-service");
        assert_eq!(custom_type, ServiceType::Custom("my-custom-service".to_string()));
        assert_eq!(custom_type.to_string(), "custom:my-custom-service");
    }
} 