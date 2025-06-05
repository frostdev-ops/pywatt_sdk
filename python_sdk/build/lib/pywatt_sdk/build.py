"""
Build information module for PyWatt Python SDK.

This module provides build information constants and utilities similar to the Rust SDK.
Build information includes git commit hash, build timestamp, and Python version.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, Optional
from dataclasses import dataclass


def _get_git_hash() -> str:
    """Get the current git commit hash (short form)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        pass
    
    # Try to get from environment variable (set by CI/CD)
    return os.getenv("PYWATT_GIT_HASH", "unknown")


def _get_build_time() -> str:
    """Get the current build timestamp in RFC3339 format."""
    # Try to get from environment variable first (set by CI/CD)
    build_time = os.getenv("PYWATT_BUILD_TIME_UTC")
    if build_time:
        return build_time
    
    # Otherwise use current time
    return datetime.now(timezone.utc).isoformat()


def _get_python_version() -> str:
    """Get the Python version used for the build."""
    # Try to get from environment variable first (set by CI/CD)
    python_version = os.getenv("PYWATT_PYTHON_VERSION")
    if python_version:
        return python_version
    
    # Otherwise use current Python version
    return f"Python {sys.version}"


# Build information constants
GIT_HASH: str = _get_git_hash()
BUILD_TIME_UTC: str = _get_build_time()
PYTHON_VERSION: str = _get_python_version()


@dataclass
class BuildInfo:
    """Build information structure."""
    
    git_hash: str
    build_time_utc: str
    python_version: str
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for JSON serialization."""
        return {
            "git_hash": self.git_hash,
            "build_time_utc": self.build_time_utc,
            "python_version": self.python_version,
        }
    
    @classmethod
    def from_constants(cls) -> 'BuildInfo':
        """Create BuildInfo from module constants."""
        return cls(
            git_hash=GIT_HASH,
            build_time_utc=BUILD_TIME_UTC,
            python_version=PYTHON_VERSION,
        )


def get_build_info() -> BuildInfo:
    """Get build information as a structured object.
    
    This is useful for including build information in health check endpoints
    or module status responses.
    
    Returns:
        BuildInfo: Structured build information
        
    Example:
        >>> info = get_build_info()
        >>> print(f"Module built from commit: {info.git_hash}")
    """
    return BuildInfo.from_constants()


def emit_build_info() -> None:
    """Emit build information for use in setup.py or build scripts.
    
    This function can be called from setup.py or other build scripts to
    capture and store build information that can be accessed at runtime.
    
    The following environment variables are used if available:
    - PYWATT_GIT_HASH: Git commit hash (short form)
    - PYWATT_BUILD_TIME_UTC: Build timestamp in RFC3339 format
    - PYWATT_PYTHON_VERSION: Python version string
    
    If these are not set, the function will attempt to determine them
    automatically.
    
    Example:
        # In setup.py or build script:
        from pywatt_sdk.build import emit_build_info
        emit_build_info()
    """
    # This function is mainly for compatibility with the Rust SDK
    # In Python, we don't have the same build-time constant injection
    # mechanism, so we just ensure the constants are computed
    global GIT_HASH, BUILD_TIME_UTC, PYTHON_VERSION
    
    # Force re-computation if needed
    if GIT_HASH == "unknown":
        GIT_HASH = _get_git_hash()
    
    if "unknown" in BUILD_TIME_UTC:
        BUILD_TIME_UTC = _get_build_time()
    
    if "unknown" in PYTHON_VERSION:
        PYTHON_VERSION = _get_python_version()
    
    # Print build info for debugging (similar to Rust SDK)
    print(f"Build info: git={GIT_HASH}, time={BUILD_TIME_UTC}, python={PYTHON_VERSION}")


def get_build_info_dict() -> Dict[str, str]:
    """Get build information as a dictionary.
    
    Convenience function for JSON serialization.
    
    Returns:
        Dict[str, str]: Build information as key-value pairs
    """
    return get_build_info().to_dict()


def get_version_info() -> Dict[str, str]:
    """Get version information including SDK version.
    
    Returns:
        Dict[str, str]: Version information including SDK version
    """
    try:
        # Try to get SDK version from package metadata
        import importlib.metadata
        sdk_version = importlib.metadata.version("pywatt-sdk")
    except (ImportError, importlib.metadata.PackageNotFoundError):
        sdk_version = "unknown"
    
    info = get_build_info_dict()
    info["sdk_version"] = sdk_version
    return info


# For backward compatibility and convenience
def get_git_hash() -> str:
    """Get the git commit hash."""
    return GIT_HASH


def get_build_time() -> str:
    """Get the build timestamp."""
    return BUILD_TIME_UTC


def get_python_version() -> str:
    """Get the Python version."""
    return PYTHON_VERSION 