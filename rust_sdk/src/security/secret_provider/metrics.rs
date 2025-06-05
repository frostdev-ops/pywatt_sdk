#![cfg(feature = "metrics")]
//! Metrics for the Secret Provider.
//!
//! This module provides metrics collection for the Secret Provider, using the
//! metrics crate. It is designed to be used with any metrics implementation
//! that supports the metrics API.

use std::time::Instant;

/// Records a secret provider operation.
///
/// # Arguments
/// * `provider` - The name of the provider (e.g., "env", "file", "memory")
/// * `operation` - The operation being performed (e.g., "get", "set", "keys")
/// * `outcome` - The outcome of the operation ("success" or "error")
pub fn record_operation(provider: &str, operation: &str, outcome: &str) {
    metrics::counter!("secret_provider_operations_total", 
        "provider" => provider.to_string(),
        "operation" => operation.to_string(),
        "outcome" => outcome.to_string()
    ).increment(1);
    
    tracing::debug!(
        provider = %provider,
        operation = %operation,
        outcome = %outcome,
        "Secret provider operation recorded"
    );
}

/// Records a secret rotation event.
///
/// # Arguments
/// * `provider` - The name of the provider that performed the rotation
/// * `count` - The number of secrets rotated
pub fn record_rotation(provider: &str, count: usize) {
    metrics::counter!("secret_provider_rotations_total",
        "provider" => provider.to_string()
    ).increment(1);
    
    metrics::histogram!("secret_provider_rotation_count",
        "provider" => provider.to_string()
    ).record(count as f64);
    
    tracing::info!(
        provider = %provider,
        count = %count,
        "Secret rotation recorded"
    );
}

/// Records cache statistics for secret client.
///
/// # Arguments
/// * `hit` - Whether the cache was hit (true) or missed (false)
pub fn record_cache_access(hit: bool) {
    let outcome = if hit { "hit" } else { "miss" };
    
    metrics::counter!("secret_cache_accesses_total",
        "outcome" => outcome.to_string()
    ).increment(1);
    
    tracing::trace!(
        hit = %hit,
        "Secret cache access recorded"
    );
}

/// Records the duration of a secret provider operation.
///
/// # Arguments
/// * `provider` - The name of the provider
/// * `operation` - The operation that was performed
/// * `duration` - The duration the operation took
pub fn record_operation_duration(provider: &str, operation: &str, duration: std::time::Duration) {
    metrics::histogram!("secret_provider_operation_duration_seconds",
        "provider" => provider.to_string(),
        "operation" => operation.to_string()
    ).record(duration.as_secs_f64());
    
    tracing::debug!(
        provider = %provider,
        operation = %operation,
        duration_ms = %duration.as_millis(),
        "Secret provider operation duration recorded"
    );
}

/// Records the current number of cached secrets.
///
/// # Arguments
/// * `count` - The current number of cached secrets
pub fn record_cache_size(count: usize) {
    metrics::gauge!("secret_cache_size_current")
        .set(count as f64);
}

/// A utility struct to measure and record operation durations.
pub struct OpTimer {
    provider: String,
    operation: String,
    start: Instant,
}

impl OpTimer {
    /// Creates a new timer for the given provider and operation.
    pub fn new(provider: impl Into<String>, operation: impl Into<String>) -> Self {
        Self {
            provider: provider.into(),
            operation: operation.into(),
            start: Instant::now(),
        }
    }

    /// Manually finish the timer and record the duration with a specific outcome.
    pub fn finish_with_outcome(self, outcome: &str) {
        let duration = self.start.elapsed();
        record_operation_duration(&self.provider, &self.operation, duration);
        record_operation(&self.provider, &self.operation, outcome);
    }

    /// Get the elapsed time without finishing the timer.
    pub fn elapsed(&self) -> std::time::Duration {
        self.start.elapsed()
    }
}

impl Drop for OpTimer {
    fn drop(&mut self) {
        let duration = self.start.elapsed();
        record_operation_duration(&self.provider, &self.operation, duration);
        // If we get here without finish_with_outcome being called, assume success
        record_operation(&self.provider, &self.operation, "success");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_op_timer_creation() {
        let timer = OpTimer::new("test_provider", "test_operation");
        assert!(!timer.provider.is_empty());
        assert!(!timer.operation.is_empty());
        
        // Test that elapsed time is reasonable
        let elapsed = timer.elapsed();
        assert!(elapsed.as_millis() < 100); // Should be very quick for this test
    }

    #[test]
    fn test_op_timer_finish_with_outcome() {
        let timer = OpTimer::new("test_provider", "test_operation");
        std::thread::sleep(std::time::Duration::from_millis(1));
        
        // This should not panic and should record metrics
        timer.finish_with_outcome("test_outcome");
    }
}
