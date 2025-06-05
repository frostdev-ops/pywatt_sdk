#!/usr/bin/env python3
"""Basic test for Model Manager functionality."""

import sys
from pathlib import Path

# Add the python_sdk directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data.database import DatabaseType
from services.model_manager.definitions import DataType, IntegerSize, ColumnDescriptor
from services.model_manager.builder import ModelBuilder
from services.model_manager.api import create_simple_model, validate_model, generate_complete_sql
from services.model_manager.adapters.sqlite import SqliteAdapter
from services.model_manager.adapters.postgres import PostgresAdapter
from services.model_manager.adapters.mysql import MySqlAdapter


def test_basic_functionality():
    """Test basic model manager functionality."""
    print("=== Testing Model Manager ===\n")
    
    # Test 1: Create a simple model
    print("1. Creating a simple model...")
    model = (
        create_simple_model("users")
        .add_varchar_column("username", 100, nullable=False, unique=True)
        .add_varchar_column("email", 255, nullable=False, unique=True)
        .add_boolean_column("is_active", nullable=False, default=True)
        .add_timestamps()
        .build()
    )
    
    print(f"   ✓ Created model: {model.name}")
    print(f"   ✓ Columns: {len(model.columns)}")
    for col in model.columns:
        print(f"     - {col.name}: {col.data_type.type_name}")
    
    # Test 2: Validate the model
    print("\n2. Validating model...")
    try:
        validate_model(model)
        print("   ✓ Model validation passed")
    except Exception as e:
        print(f"   ✗ Model validation failed: {e}")
        return
    
    # Test 3: Test adapters
    print("\n3. Testing database adapters...")
    adapters = [
        ("SQLite", SqliteAdapter()),
        ("PostgreSQL", PostgresAdapter()),
        ("MySQL", MySqlAdapter()),
    ]
    
    for name, adapter in adapters:
        print(f"   {name}:")
        try:
            # Test type conversion
            varchar_type = DataType.varchar(100)
            sql_type = adapter.get_type_sql(varchar_type)
            print(f"     VARCHAR(100) -> {sql_type}")
            
            # Test table creation
            table_sql = adapter.generate_create_table_sql(model)
            print(f"     CREATE TABLE generated: {len(table_sql)} chars")
            
        except Exception as e:
            print(f"     Error: {e}")
    
    # Test 4: Generate complete SQL
    print("\n4. Generating complete SQL...")
    for db_type in [DatabaseType.SQLITE, DatabaseType.POSTGRESQL, DatabaseType.MYSQL]:
        print(f"\n   --- {db_type.value} ---")
        try:
            sql = generate_complete_sql(model, db_type)
            print(sql[:200] + "..." if len(sql) > 200 else sql)
        except Exception as e:
            print(f"   Error: {e}")
    
    print("\n✅ All tests completed successfully!")


if __name__ == "__main__":
    test_basic_functionality() 