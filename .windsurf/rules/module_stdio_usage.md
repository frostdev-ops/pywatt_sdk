---
trigger: always_on
description: 
globs: 
---
# Component: Module stdio Usage

## Component Type
Utility / Cursor Rule

## File Path
`.cursor/rules/module_stdio_usage.mdc`

## Purpose
Defines the discipline for using `stdout` exclusively for IPC JSON messages and `stderr` for all logs in PyWatt modules, ensuring the orchestrator can reliably parse messages.

## Rules
1. **stdout = IPC ONLY**
   - Only emit structured JSON messages for orchestrator communication (e.g., `AnnounceBlob`).
   - Use `send_announce()` or equivalent to write IPC to `stdout`.
2. **stderr = Logging**
   - All application logs (info, warn, error) must go to `stderr`.
   - Configure `tracing_subscriber` (or your logger) to target `stderr`.

## Correct Usage
```rust
use pywatt_module_utils::{init_module, send_announce, AnnounceBlob, EndpointInfo};
use tracing::info;

// Configure logging to stderr with redaction
init_module();
info!("Starting module");           // goes to stderr

// Later: announce on stdout
let announce = AnnounceBlob { /* ... */ };
send_announce(&announce)?;          // goes to stdout
```

## Incorrect Usage
```rust
// BAD: logs to stdout, breaks IPC protocol
println!("Module started");        // DO NOT use

// BAD: writes non-IPC JSON to stdout
println!("{\"level\":\"INFO\", \"msg\":\"Starting\"}");
```

## Examples of Tracing Setup
```rust
tracing_subscriber::fmt()
    .json()
    .with_writer(std::io::stderr)
    .init();
```  

## Best Practices
- Keep each IPC JSON message on a single line with no extra whitespace or newlines.
- Do not mix logs and IPC in the same stream.
- Reserve any `println!` calls strictly for confirmed IPC messages.
