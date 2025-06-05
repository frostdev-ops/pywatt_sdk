---
trigger: always_on
description: 
globs: 
---
# Cursor Rules for `pywatt_sdk`

## Rule: read_init
Public async function `read_init()` reads the initial handshake JSON from stdin and returns an `OrchestratorInit` or `InitError`.

## Rule: send_announce
Public function `send_announce()` serializes and prints a `ModuleAnnounce` JSON blob to stdout, returning `AnnounceError` on failure.

## Rule: process_ipc_messages
Public async function `process_ipc_messages()` listens on stdin for runtime IPC messages (`Secret`, `Rotated`, `Shutdown`) and delegates to `SecretClient`.

## Rule: get_module_secret_client
Public async function `get_module_secret_client()` constructs a `SecretClient` connected to the orchestrator's secret API.

## Rule: get_secret
Public async function `get_secret()` fetches a named secret from the `SecretClient`, registers it for redaction, and returns a `Secret`.

## Rule: get_secrets
Public async function `get_secrets()` fetches a list of secrets and returns them as a vector.

## Rule: subscribe_secret_rotations
Public async function `subscribe_secret_rotations()` spawns a background task to handle secret rotation notifications and invokes a user-provided callback.

## Rule: AppState::new
Public constructor `AppState::new(module_id, orchestrator_api, secret_client, user_state)` creates shared application state.

## Rule: ModuleBuilder::build
Builder method `ModuleBuilder<T>::build()` performs handshake, secrets fetch, announcement, and spawns the IPC loop, returning `(AppState<T>, JoinHandle<()>)`.

## Rule: serve_module
Public async function `serve_module()` bootstraps logging, handshake, secrets, announcement, and serves an Axum `Router`, returning `ServeError` on failure.

## Rule: init_module
Public function `init_module()` configures tracing subscriber with JSON logs to stderr and secret redaction.

## Rule: bootstrap_module
Internal helper `bootstrap_module()` that implements the core handshake and bootstrap flow (re-exported for advanced use).
