# Independent Channel Bootstrap Guide

This document explains how to use the enhanced independent channel bootstrap functionality introduced in Phase 2 of the Wattson Module Communication Refactor.

## Overview

The PyWatt SDK now supports independent TCP and IPC (Unix Domain Socket) communication channels that can operate completely independently. Modules can use:

- **TCP only** - Traditional network-based communication
- **IPC only** - High-performance local Unix Domain Socket communication  
- **Both channels** - Automatic selection based on target and preferences
- **Neither** - Fallback to stdin/stdout IPC for control messages

## Key Features

### Independent Channel Operation
- TCP and IPC channels operate completely independently
- Failure of one channel doesn't affect the other
- Each channel has its own message processing task
- Graceful degradation when preferred channels are unavailable

### Channel Preferences
- Configure which channels to use and prioritize
- Smart routing based on target (local vs remote)
- Automatic fallback between channels
- Fine-grained control over channel behavior

### Enhanced Configuration
- Orchestrator provides channel configurations via enhanced InitBlob
- Modules can specify channel requirements (optional vs required)
- Support for channel-specific security settings
- Backward compatibility with legacy TCP-only initialization

## Usage Examples

### Basic Usage with Default Preferences

```rust
use pywatt_sdk::core::bootstrap::bootstrap_module;
use pywatt_sdk::{AnnouncedEndpoint};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let secret_keys = vec!["DATABASE_URL".to_string()];
    let endpoints = vec![
        AnnouncedEndpoint {
            path: "/health".to_string(),
            methods: vec!["GET".to_string()],
            auth: None,
        }
    ];

    // Use default channel preferences (both TCP and IPC enabled)
    let (app_state, join_handle) = bootstrap_module(
        secret_keys,
        endpoints,
        |_init, _secrets| MyAppState::new(),
        None, // Use default preferences
    ).await?;

    // Module is now running with independent channels
    join_handle.await?;
    Ok(())
}
```

### TCP-Only Configuration

```rust
use pywatt_sdk::communication::ChannelPreferences;

let preferences = Some(ChannelPreferences::tcp_only());

let (app_state, join_handle) = bootstrap_module(
    secret_keys,
    endpoints,
    state_builder,
    preferences,
).await?;
```

### IPC-Only Configuration

```rust
use pywatt_sdk::communication::ChannelPreferences;

let preferences = Some(ChannelPreferences::ipc_only());

let (app_state, join_handle) = bootstrap_module(
    secret_keys,
    endpoints,
    state_builder,  
    preferences,
).await?;
```

### Custom Channel Preferences

```rust
use pywatt_sdk::communication::ChannelPreferences;

let preferences = Some(ChannelPreferences {
    use_tcp: true,
    use_ipc: true,
    prefer_ipc_for_local: true,    // Prefer IPC for local communication
    prefer_tcp_for_remote: true,   // Prefer TCP for remote communication
    enable_fallback: true,         // Allow fallback to other channel
});
```

## Smart Channel Selection

The AppState provides intelligent channel selection methods:

### Automatic Channel Selection

```rust
use pywatt_sdk::message::EncodedMessage;
use pywatt_sdk::communication::ChannelPreferences;

// Send message with automatic channel selection
let message = EncodedMessage::new(my_data);
let preferences = Some(ChannelPreferences::prefer_ipc());

app_state.send_message("target_module", message, preferences).await?;
```

### Explicit Channel Selection

```rust
use pywatt_sdk::communication::ChannelType;

// Send via specific channel
app_state.send_message_via_channel(
    ChannelType::Tcp, 
    message
).await?;

app_state.send_message_via_channel(
    ChannelType::Ipc,
    message  
).await?;
```

### Channel Introspection

```rust
// Check available channels
let channels = app_state.available_channels();
println!("Available channels: {:?}", channels);

// Check specific channel availability
if app_state.has_channel(ChannelType::Ipc) {
    println!("IPC channel is available");
}

// Get channel capabilities
if let Some(caps) = app_state.channel_capabilities(ChannelType::Tcp) {
    println!("TCP supports file transfer: {}", caps.file_transfer);
}

// Check channel health
let health = app_state.channel_health().await;
for (channel_type, is_healthy) in health {
    println!("{:?} channel healthy: {}", channel_type, is_healthy);
}

// Get recommended channel for target
let recommended = app_state.recommend_channel("127.0.0.1:8080", None);
println!("Recommended channel: {:?}", recommended);
```

## Enhanced InitBlob Configuration

The orchestrator can provide enhanced channel configurations:

```json
{
  "orchestrator_api": "http://localhost:9900",
  "module_id": "my-module",
  "env": {},
  "listen": "127.0.0.1:0",
  "tcp_channel": {
    "address": "127.0.0.1:9901",
    "tls_enabled": false,
    "required": false
  },
  "ipc_channel": {
    "socket_path": "/tmp/wattson_my-module.sock",
    "required": false
  },
  "auth_token": null,
  "security_level": "None"
}
```

## Error Handling

The bootstrap process provides specific errors for channel failures:

```rust
use pywatt_sdk::core::bootstrap::BootstrapError;

match bootstrap_module(secret_keys, endpoints, state_builder, preferences).await {
    Ok((app_state, handle)) => {
        // Success - module running with available channels
    }
    Err(BootstrapError::RequiredChannelFailed { channel_type, error }) => {
        eprintln!("Required {} channel failed: {}", channel_type, error);
    }
    Err(BootstrapError::NoChannelsAvailable) => {
        eprintln!("No communication channels available");
    }
    Err(e) => {
        eprintln!("Bootstrap failed: {}", e);
    }
}
```

## Channel Capabilities

Each channel type supports different capabilities:

```rust
use pywatt_sdk::communication::ChannelCapabilities;

// TCP channels support all capabilities including file transfer
let tcp_caps = ChannelCapabilities::tcp_standard();
assert!(tcp_caps.file_transfer);

// IPC channels support all capabilities for local communication
let ipc_caps = ChannelCapabilities::ipc_standard(); 
assert!(ipc_caps.module_messaging);
```

## Backward Compatibility

The new system maintains full backward compatibility:

- Modules using the old `bootstrap_module` signature will continue to work
- Legacy TCP-only initialization is supported automatically
- Existing modules don't need changes unless they want new functionality
- Use `bootstrap_module_legacy` for explicit legacy behavior

## Migration Guide

To migrate existing modules to use independent channels:

1. **Update bootstrap call** - Add `ChannelPreferences` parameter
2. **Update message sending** - Use new `send_message` methods for intelligent routing
3. **Handle new errors** - Add handling for channel-specific errors
4. **Test thoroughly** - Verify behavior with different channel configurations

## Performance Considerations

- **IPC channels** provide lowest latency for local communication
- **TCP channels** support cross-host communication and file transfer
- **Dual channels** enable optimal routing but use more resources
- **Channel selection** has minimal overhead but can be cached for hot paths

## Security

- Independent channels can have different security configurations
- IPC channels inherit Unix socket permissions
- TCP channels support TLS encryption (when enabled)
- Authentication tokens can be channel-specific

## Best Practices

1. **Use default preferences** for most modules unless specific requirements exist
2. **Enable fallback** to ensure reliability in diverse environments
3. **Check channel health** periodically for monitoring
4. **Log channel selection** decisions for debugging
5. **Test all channel combinations** your module supports
6. **Use IPC for local**, TCP for remote communication when possible
7. **Handle channel failures gracefully** with appropriate retry logic 