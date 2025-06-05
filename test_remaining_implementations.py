#!/usr/bin/env python3
"""
Test script to verify all remaining PyWatt SDK implementations.

This script tests the components mentioned in IMPLEMENTATION_STATUS.md
to verify they are properly implemented and working.
"""

import sys
import traceback
from typing import List, Dict, Any


def test_build_info():
    """Test build information system."""
    print("Testing build information system...")
    
    try:
        from pywatt_sdk.build import (
            get_build_info, get_build_info_dict, get_version_info,
            GIT_HASH, BUILD_TIME_UTC, PYTHON_VERSION
        )
        
        # Test constants
        assert isinstance(GIT_HASH, str)
        assert isinstance(BUILD_TIME_UTC, str)
        assert isinstance(PYTHON_VERSION, str)
        print(f"  ✓ Constants: git={GIT_HASH}, time={BUILD_TIME_UTC[:19]}, python={PYTHON_VERSION[:20]}")
        
        # Test structured info
        info = get_build_info()
        assert hasattr(info, 'git_hash')
        assert hasattr(info, 'build_time_utc')
        assert hasattr(info, 'python_version')
        print(f"  ✓ BuildInfo object: {info}")
        
        # Test dict conversion
        info_dict = get_build_info_dict()
        assert isinstance(info_dict, dict)
        assert 'git_hash' in info_dict
        print(f"  ✓ Dict conversion: {len(info_dict)} fields")
        
        # Test version info
        version_info = get_version_info()
        assert isinstance(version_info, dict)
        assert 'sdk_version' in version_info
        print(f"  ✓ Version info: {version_info.get('sdk_version', 'unknown')}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Build info test failed: {e}")
        traceback.print_exc()
        return False


def test_router_discovery():
    """Test router discovery system."""
    print("Testing router discovery system...")
    
    try:
        from pywatt_sdk.services.router_discovery import (
            announce_from_router, discover_endpoints, discover_endpoints_advanced,
            DiscoveredEndpoint, normalize_method, deduplicate_endpoints
        )
        
        # Test utility functions
        assert normalize_method("get") == "GET"
        assert normalize_method("POST") == "POST"
        print("  ✓ Method normalization works")
        
        # Test endpoint deduplication
        endpoints = [
            DiscoveredEndpoint("/test", ["GET"]),
            DiscoveredEndpoint("/test", ["POST"]),
            DiscoveredEndpoint("/other", ["GET"])
        ]
        deduped = deduplicate_endpoints(endpoints)
        assert len(deduped) == 2
        assert "/test" in [ep.path for ep in deduped]
        test_endpoint = next(ep for ep in deduped if ep.path == "/test")
        assert "GET" in test_endpoint.methods
        assert "POST" in test_endpoint.methods
        print("  ✓ Endpoint deduplication works")
        
        # Test with mock app (no framework dependencies)
        class MockApp:
            pass
        
        mock_app = MockApp()
        endpoints = announce_from_router(mock_app)
        assert isinstance(endpoints, list)
        print(f"  ✓ Mock app discovery: {len(endpoints)} endpoints")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Router discovery test failed: {e}")
        traceback.print_exc()
        return False


def test_database_implementations():
    """Test database implementations."""
    print("Testing database implementations...")
    
    try:
        # Test PostgreSQL implementation
        from pywatt_sdk.data.postgresql import PostgresConnection
        print("  ✓ PostgreSQL implementation imported")
        
        # Test MySQL implementation  
        from pywatt_sdk.data.mysql import MySqlConnection
        print("  ✓ MySQL implementation imported")
        
        # Test enhanced database factory
        from pywatt_sdk.data.database import create_database_connection, SqliteConnection
        
        # Test SQLite config
        sqlite_config = {
            "type": "sqlite",
            "database": ":memory:"
        }
        
        # This should work without external dependencies
        conn = create_database_connection(sqlite_config)
        assert isinstance(conn, SqliteConnection)
        print("  ✓ SQLite connection factory works")
        
        # Test PostgreSQL config (should create object but not connect)
        postgres_config = {
            "type": "postgresql", 
            "host": "localhost",
            "database": "test",
            "user": "test",
            "password": "test"
        }
        
        postgres_conn = create_database_connection(postgres_config)
        assert isinstance(postgres_conn, PostgresConnection)
        print("  ✓ PostgreSQL connection factory works")
        
        # Test MySQL config (should create object but not connect)
        mysql_config = {
            "type": "mysql",
            "host": "localhost", 
            "database": "test",
            "user": "test",
            "password": "test"
        }
        
        mysql_conn = create_database_connection(mysql_config)
        assert isinstance(mysql_conn, MySqlConnection)
        print("  ✓ MySQL connection factory works")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Database implementations test failed: {e}")
        traceback.print_exc()
        return False


def test_cache_implementations():
    """Test cache implementations."""
    print("Testing cache implementations...")
    
    try:
        # Test Redis implementation
        from pywatt_sdk.data.redis_cache import RedisCache
        print("  ✓ Redis cache implementation imported")
        
        # Test Memcached implementation
        from pywatt_sdk.data.memcached_cache import MemcachedCache  
        print("  ✓ Memcached cache implementation imported")
        
        # Test enhanced cache factory
        from pywatt_sdk.data.cache import create_cache_service, InMemoryCache
        
        # Test in-memory cache (should work without external dependencies)
        memory_config = {
            "type": "memory",
            "max_size": 1000
        }
        
        cache = create_cache_service(memory_config)
        assert isinstance(cache, InMemoryCache)
        print("  ✓ In-memory cache factory works")
        
        # Test Redis config (should create object but not connect)
        redis_config = {
            "type": "redis",
            "host": "localhost",
            "port": 6379,
            "db": 0
        }
        
        redis_cache = create_cache_service(redis_config)
        assert isinstance(redis_cache, RedisCache)
        print("  ✓ Redis cache factory works")
        
        # Test Memcached config (should create object but not connect)
        memcached_config = {
            "type": "memcached",
            "servers": ["localhost:11211"]
        }
        
        memcached_cache = create_cache_service(memcached_config)
        assert isinstance(memcached_cache, MemcachedCache)
        print("  ✓ Memcached cache factory works")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Cache implementations test failed: {e}")
        traceback.print_exc()
        return False


def test_existing_implementations():
    """Test that existing implementations are still working."""
    print("Testing existing implementations...")
    
    try:
        # Test core components
        from pywatt_sdk.core import AppState, AppConfig
        from pywatt_sdk.communication.ipc import read_init, send_announce
        from pywatt_sdk.security.secret_client import SecretClient
        print("  ✓ Core components imported successfully")
        
        # Test HTTP communication
        from pywatt_sdk.communication.http_ipc import HttpIpcRouter
        from pywatt_sdk.communication.http_tcp import HttpTcpClient
        from pywatt_sdk.communication.port_negotiation import PortNegotiationManager
        print("  ✓ HTTP communication components imported successfully")
        
        # Test JWT auth
        from pywatt_sdk.security.jwt_auth import JwtValidator, JwtConfig
        print("  ✓ JWT authentication components imported successfully")
        
        # Test CLI
        from pywatt_sdk.cli.scaffolder import create_module_template
        print("  ✓ CLI scaffolder imported successfully")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Existing implementations test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all tests and report results."""
    print("PyWatt SDK Implementation Verification")
    print("=" * 50)
    
    tests = [
        ("Build Information System", test_build_info),
        ("Router Discovery System", test_router_discovery), 
        ("Database Implementations", test_database_implementations),
        ("Cache Implementations", test_cache_implementations),
        ("Existing Implementations", test_existing_implementations),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"  ✗ Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Results Summary:")
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {test_name}")
        if success:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All implementations verified successfully!")
        return 0
    else:
        print("❌ Some implementations need attention")
        return 1


if __name__ == "__main__":
    sys.exit(main()) 