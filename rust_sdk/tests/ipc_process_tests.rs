#[cfg(test)]
mod tests {
    use pywatt_sdk::communication::ipc_types::{OrchestratorToModule, RotatedNotification, SecretValueResponse};
    use pywatt_sdk::security::secret_client::{RequestMode, SecretClient};
    use std::sync::Arc;
    use tokio::sync::mpsc;

    struct MockStdin {
        receiver: mpsc::Receiver<String>,
    }

    impl MockStdin {
        fn new(receiver: mpsc::Receiver<String>) -> Self {
            Self { receiver }
        }

        async fn read_line(&mut self, buf: &mut String) -> std::io::Result<usize> {
            if let Some(line) = self.receiver.recv().await {
                buf.push_str(&line);
                Ok(line.len())
            } else {
                Ok(0) // EOF
            }
        }
    }

    async fn run_ipc_loop(mut mock_stdin: MockStdin, client: Arc<SecretClient>) {
        let mut line = String::new();

        loop {
            line.clear();
            match mock_stdin.read_line(&mut line).await {
                Ok(0) => {
                    // EOF: orchestrator closed stdin
                    break;
                }
                Ok(_) => {
                    let trimmed = line.trim_end();
                    match serde_json::from_str::<OrchestratorToModule>(trimmed) {
                        Ok(msg) => match msg {
                            OrchestratorToModule::Secret(_) | OrchestratorToModule::Rotated(_) => {
                                // Let SecretClient handle secret and rotation
                                if let Err(e) = client.process_server_message(trimmed).await {
                                    eprintln!("Error processing secret RPC: {}", e);
                                }
                            }
                            OrchestratorToModule::Shutdown => {
                                break;
                            }
                            OrchestratorToModule::Init(_) => {
                                // ignore extra init messages
                            }
                            OrchestratorToModule::ServiceResponse(_)
                            | OrchestratorToModule::ServiceOperationResult(_)
                            | OrchestratorToModule::HttpRequest(_) => {
                                // ignore service-related and HTTP request messages in test IPC loop
                            }
                            _ => {}
                        },
                        Err(e) => {
                            eprintln!("Failed to parse IPC message: {} raw: {}", e, trimmed);
                        }
                    }
                }
                Err(e) => {
                    eprintln!("Error reading IPC stdin: {}", e);
                    break;
                }
            }
        }
    }

    #[tokio::test]
    async fn test_process_secret_message() {
        let (sender, receiver) = mpsc::channel(10);
        let mock_stdin = MockStdin::new(receiver);

        // Create a secret client
        let client = SecretClient::new_dummy();

        let client_clone = Arc::new(client);

        // Start the IPC loop in a separate task
        let ipc_task = tokio::spawn(run_ipc_loop(mock_stdin, client_clone.clone()));

        // Send a secret response message
        let secret_msg = OrchestratorToModule::Secret(SecretValueResponse {
            name: "NEW_SECRET".to_string(),
            value: "secret_value".to_string(),
            rotation_id: None,
        });

        let json = serde_json::to_string(&secret_msg).unwrap();
        sender.send(format!("{}\n", json)).await.unwrap();

        // Send shutdown message to terminate the loop
        let shutdown_msg = OrchestratorToModule::Shutdown;
        let json = serde_json::to_string(&shutdown_msg).unwrap();
        sender.send(format!("{}\n", json)).await.unwrap();

        // Wait for the loop to finish
        ipc_task.await.unwrap();

        // Verify the secret was stored in the client
        let result = client_clone
            .get_secret("NEW_SECRET", RequestMode::CacheThenRemote)
            .await;
        assert!(result.is_ok());

        // Use expose_secret to compare the secret value
        let secret_string = result.unwrap();
        assert_eq!(
            secrecy::ExposeSecret::expose_secret(&secret_string),
            "secret_value"
        );
    }

    #[tokio::test]
    async fn test_process_rotation_message() {
        let (sender, receiver) = mpsc::channel(10);
        let mock_stdin = MockStdin::new(receiver);

        // Create a separate channel for verification
        let (verify_tx, verify_rx) = mpsc::channel::<Vec<String>>(1);

        // Create a secret client with verification capability
        let client = SecretClient::new_dummy();

        // Note: This test verifies rotation handling with the current dummy client implementation
        let client_clone = Arc::new(client);

        // Start the IPC loop in a separate task
        let ipc_task = tokio::spawn(run_ipc_loop(mock_stdin, client_clone.clone()));

        // Send a rotation notification
        let rotated_msg = OrchestratorToModule::Rotated(RotatedNotification {
            keys: vec!["SECRET1".to_string(), "SECRET2".to_string()],
            rotation_id: "rotation-123".to_string(),
        });

        let json = serde_json::to_string(&rotated_msg).unwrap();
        sender.send(format!("{}\n", json)).await.unwrap();

        // Provide new secret values after rotation notification
        let secret1_msg = OrchestratorToModule::Secret(SecretValueResponse {
            name: "SECRET1".to_string(),
            value: "new_value1".to_string(),
            rotation_id: Some("rotation-123".to_string()),
        });

        let json = serde_json::to_string(&secret1_msg).unwrap();
        sender.send(format!("{}\n", json)).await.unwrap();

        let secret2_msg = OrchestratorToModule::Secret(SecretValueResponse {
            name: "SECRET2".to_string(),
            value: "new_value2".to_string(),
            rotation_id: Some("rotation-123".to_string()),
        });

        let json = serde_json::to_string(&secret2_msg).unwrap();
        sender.send(format!("{}\n", json)).await.unwrap();

        // Send shutdown message to terminate the loop
        let shutdown_msg = OrchestratorToModule::Shutdown;
        let json = serde_json::to_string(&shutdown_msg).unwrap();
        sender.send(format!("{}\n", json)).await.unwrap();

        // Wait for the loop to finish
        ipc_task.await.unwrap();

        // Verify the secret values were updated
        let secret1 = client_clone
            .get_secret("SECRET1", RequestMode::CacheThenRemote)
            .await
            .unwrap();
        let secret2 = client_clone
            .get_secret("SECRET2", RequestMode::CacheThenRemote)
            .await
            .unwrap();

        // Use expose_secret to compare the secret values
        assert_eq!(secrecy::ExposeSecret::expose_secret(&secret1), "new_value1");
        assert_eq!(secrecy::ExposeSecret::expose_secret(&secret2), "new_value2");
    }

    #[tokio::test]
    async fn test_process_invalid_message() {
        let (sender, receiver) = mpsc::channel(10);
        let mock_stdin = MockStdin::new(receiver);

        let client = SecretClient::new_dummy();
        let client_clone = Arc::new(client);

        // Start the IPC loop in a separate task
        let ipc_task = tokio::spawn(run_ipc_loop(mock_stdin, client_clone.clone()));

        // Send an invalid JSON message
        sender.send("{ invalid json }\n".to_string()).await.unwrap();

        // Send shutdown message to terminate the loop
        let shutdown_msg = OrchestratorToModule::Shutdown;
        let json = serde_json::to_string(&shutdown_msg).unwrap();
        sender.send(format!("{}\n", json)).await.unwrap();

        // Wait for the loop to finish - test passes if we don't crash
        ipc_task.await.unwrap();
    }
}
