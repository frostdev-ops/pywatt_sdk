//! Integration tests for independent channel bootstrap functionality.

use pywatt_sdk::core::bootstrap::bootstrap_module;
use pywatt_sdk::communication::{ChannelPreferences, ChannelType};
use pywatt_sdk::{AnnouncedEndpoint, OrchestratorInit};
use secrecy::SecretString;

/// Mock state for testing
#[derive(Debug, Clone)]
struct TestState {
    data: String,
}

/// Mock state builder for testing
fn test_state_builder(_init: &OrchestratorInit, _secrets: Vec<SecretString>) -> TestState {
    TestState {
        data: "test_data".to_string(),
    }
}

#[tokio::test]
async fn test_channel_preferences_tcp_only() {
    // This test verifies that TCP-only preferences work correctly
    let preferences = ChannelPreferences::tcp_only();
    
    assert!(preferences.use_tcp);
    assert!(!preferences.use_ipc);
    assert!(!preferences.prefer_ipc_for_local);
    assert!(preferences.prefer_tcp_for_remote);
    assert!(!preferences.enable_fallback);
}

#[tokio::test]
async fn test_channel_preferences_ipc_only() {
    // This test verifies that IPC-only preferences work correctly
    let preferences = ChannelPreferences::ipc_only();
    
    assert!(!preferences.use_tcp);
    assert!(preferences.use_ipc);
    assert!(preferences.prefer_ipc_for_local);
    assert!(!preferences.prefer_tcp_for_remote);
    assert!(!preferences.enable_fallback);
}

#[tokio::test]
async fn test_channel_preferences_default() {
    // This test verifies that default preferences allow both channels
    let preferences = ChannelPreferences::default();
    
    assert!(preferences.use_tcp);
    assert!(preferences.use_ipc);
    assert!(preferences.prefer_ipc_for_local);
    assert!(preferences.prefer_tcp_for_remote);
    assert!(preferences.enable_fallback);
}

#[tokio::test]
async fn test_app_state_channel_methods() {
    use pywatt_sdk::core::state::AppState;
    use pywatt_sdk::secret_client::SecretClient;
    use pywatt_sdk::communication::ChannelCapabilities;
    use std::sync::Arc;
    
    // Create a mock secret client
    let secret_client = Arc::new(SecretClient::new_dummy());
    
    // Create test state
    let mut app_state = AppState::new(
        "test_module".to_string(),
        "http://localhost:9900".to_string(),
        secret_client,
        TestState { data: "test".to_string() },
    );
    
    // Test initial state - no channels
    assert!(app_state.available_channels().is_empty());
    assert!(!app_state.has_channel(ChannelType::Tcp));
    assert!(!app_state.has_channel(ChannelType::Ipc));
    
    // Set capabilities
    app_state.tcp_capabilities = ChannelCapabilities::tcp_standard();
    app_state.ipc_capabilities = ChannelCapabilities::ipc_standard();
    
    // Test capabilities
    assert_eq!(app_state.tcp_capabilities.module_messaging, true);
    assert_eq!(app_state.ipc_capabilities.file_transfer, true);
}

#[tokio::test]
async fn test_channel_recommendation() {
    use pywatt_sdk::core::state::AppState;
    use pywatt_sdk::secret_client::SecretClient;
    use std::sync::Arc;
    
    // Create a mock secret client
    let secret_client = Arc::new(SecretClient::new_dummy());
    
    // Create test state with no channels initially
    let app_state = AppState::new(
        "test_module".to_string(),
        "http://localhost:9900".to_string(),
        secret_client,
        TestState { data: "test".to_string() },
    );
    
    // Test recommendation with no channels
    let prefs = ChannelPreferences::default();
    assert!(app_state.recommend_channel("localhost:8080", Some(prefs)).is_none());
    
    // Test local target recommendation (would prefer IPC if available)
    let prefs = ChannelPreferences::prefer_ipc();
    assert!(app_state.recommend_channel("127.0.0.1:8080", Some(prefs)).is_none());
    
    // Test remote target recommendation (would prefer TCP if available)
    let prefs = ChannelPreferences::prefer_tcp();
    assert!(app_state.recommend_channel("192.168.1.100:8080", Some(prefs)).is_none());
}

#[tokio::test]
async fn test_enhanced_init_blob_parsing() {
    use pywatt_sdk::ipc_types::{InitBlob, TcpChannelConfig, IpcChannelConfig, SecurityLevel};
    use std::path::PathBuf;
    
    // Create an enhanced InitBlob with channel configurations
    let init_blob = InitBlob::new(
        "http://localhost:9900".to_string(),
        "test_module".to_string(),
        pywatt_sdk::ipc_types::ListenAddress::Tcp("127.0.0.1:8080".parse().unwrap()),
    )
    .with_tcp_channel(TcpChannelConfig::new("127.0.0.1:9901".parse().unwrap()))
    .with_ipc_channel(IpcChannelConfig::new(PathBuf::from("/tmp/test.sock")))
    .with_security_level(SecurityLevel::None);
    
    // Verify the channel configurations
    assert!(init_blob.has_channels());
    assert!(!init_blob.has_required_channels());
    
    if let Some(tcp_config) = &init_blob.tcp_channel {
        assert_eq!(tcp_config.address.port(), 9901);
        assert!(!tcp_config.tls_enabled);
        assert!(!tcp_config.required);
    }
    
    if let Some(ipc_config) = &init_blob.ipc_channel {
        assert_eq!(ipc_config.socket_path, PathBuf::from("/tmp/test.sock"));
        assert!(!ipc_config.required);
    }
}

/// Mock test to demonstrate bootstrap error handling for required channels
#[tokio::test]
async fn test_bootstrap_error_types() {
    use pywatt_sdk::core::bootstrap::BootstrapError;
    
    // Test required channel failure error
    let error = BootstrapError::RequiredChannelFailed {
        channel_type: "TCP".to_string(),
        error: "Connection refused".to_string(),
    };
    
    assert!(error.to_string().contains("TCP"));
    assert!(error.to_string().contains("Connection refused"));
    
    // Test no channels available error
    let error = BootstrapError::NoChannelsAvailable;
    assert!(error.to_string().contains("No channels available"));
}

#[cfg(feature = "ipc_channel")]
#[tokio::test]
async fn test_ipc_channel_config() {
    use pywatt_sdk::communication::IpcConnectionConfig;
    use std::path::PathBuf;
    use std::time::Duration;
    
    // Test IPC connection configuration
    let config = IpcConnectionConfig::new("/tmp/test.sock")
        .with_timeout(Duration::from_secs(10));
    
    assert_eq!(config.socket_path, PathBuf::from("/tmp/test.sock"));
    assert_eq!(config.timeout, Duration::from_secs(10));
}

/// Integration test that verifies the complete bootstrap flow with mock orchestrator
/// Note: This is a conceptual test - in practice, we'd need a mock orchestrator
#[tokio::test]
async fn test_bootstrap_flow_concept() {
    // This test demonstrates what a full bootstrap test would look like
    // In practice, we'd need to set up a mock orchestrator that:
    // 1. Sends an InitBlob via stdin
    // 2. Accepts announcement via stdout  
    // 3. Provides TCP/IPC endpoints for channel connection
    
    let secret_keys = vec!["TEST_SECRET".to_string()];
    let endpoints = vec![AnnouncedEndpoint {
        path: "/health".to_string(),
        methods: vec!["GET".to_string()],
        auth: None,
    }];
    
    let preferences = Some(ChannelPreferences::tcp_only());
    
    // This would typically fail because we don't have a real orchestrator
    // but it demonstrates the API
    let result = bootstrap_module(
        secret_keys,
        endpoints,
        test_state_builder,
        preferences,
    ).await;
    
    // In a real test environment with a mock orchestrator, we'd expect success
    // For now, we just verify that the function is callable with the right signature
    assert!(result.is_err()); // Expected to fail without real orchestrator
} 