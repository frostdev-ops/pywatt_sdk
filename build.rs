use chrono;
use std::process::Command;

/// Build script that captures build metadata to expose at runtime through env vars.
/// 
/// This script captures:
/// - Git commit hash (short form)
/// - Build timestamp (UTC in RFC3339 format)
/// - Rust compiler version
fn main() {
    // Git hash - get the current commit hash or use "unknown" if git command fails
    let git_hash = Command::new("git")
        .args(["rev-parse", "--short", "HEAD"])
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|e| {
            eprintln!("Warning: Failed to get git hash: {}", e);
            "unknown".to_string()
        });

    // Build timestamp in RFC3339 format
    let build_time = chrono::Utc::now().to_rfc3339();

    // Rust compiler version
    let rustc_version = Command::new("rustc")
        .arg("--version")
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|e| {
            eprintln!("Warning: Failed to get rustc version: {}", e); 
            "unknown".to_string()
        });

    // Define environment variables available at runtime
    println!("cargo:rustc-env=PYWATT_GIT_HASH={}", git_hash);
    println!("cargo:rustc-env=PYWATT_BUILD_TIME_UTC={}", build_time);
    println!("cargo:rustc-env=PYWATT_RUSTC_VERSION={}", rustc_version);

    // Instruct Cargo to rerun this build script if git HEAD changes
    println!("cargo:rerun-if-changed=.git/HEAD");
    println!("cargo:rerun-if-changed=.git/refs/heads");
}
