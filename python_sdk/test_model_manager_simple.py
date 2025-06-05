#!/usr/bin/env python3
"""Simple test for the Model Manager functionality."""

# Direct imports to avoid dependency issues
from services.model_manager.definitions import (
    ModelDescriptor,
    ColumnDescriptor,
    DataType,
    IntegerSize,
    ReferentialAction,
)
from services.model_manager.builder import ModelBuilder
from services.model_manager.api import (
    create_simple_model,
    validate_model,
    generate_complete_sql,
)
from services.model_manager.adapters import SqliteAdapter, PostgresAdapter, MySqlAdapter
from data.database import DatabaseType


def test_basic_model():
    """Test creating a basic model."""
    print("=== Testing Basic Model Creation ===\n")
    
    # Create a simple user model
    model = (
        create_simple_model("users")
        .add_varchar_column("username", 100, nullable=False, unique=True)
        .add_varchar_column("email", 255, nullable=False, unique=True)
        .add_boolean_column("is_active", nullable=False, default=True)
        .add_timestamps()
        .build()
    )
    
    print(f"Created model: {model.name}")
    print(f"Columns: {len(model.columns)}")
    for col in model.columns:
        print(f"  - {col.name}: {col.data_type.type_name}")
    
    # Validate the model
    try:
        validate_model(model)
        print("\n✓ Model validation passed")
    except Exception as e:
        print(f"\n✗ Model validation failed: {e}")
    
    return model


def test_adapters():
    """Test database adapters."""
    print("\n\n=== Testing Database Adapters ===\n")
    
    # Test each adapter
    adapters = [
        ("SQLite", SqliteAdapter()),
        ("PostgreSQL", PostgresAdapter()),
        ("MySQL", MySqlAdapter()),
    ]
    
    # Simple column for testing
    column = ColumnDescriptor(
        name="test_col",
        data_type=DataType.varchar(100),
        is_nullable=False,
        is_primary_key=False,
        is_unique=False,
        default_value=None,
        auto_increment=False,
        comment=None,
        constraints=[],
    )
    
    for name, adapter in adapters:
        print(f"{name} adapter:")
        try:
            type_sql = adapter.get_type_sql(column.data_type)
            print(f"  VARCHAR(100) -> {type_sql}")
            print(f"  Supports schemas: {adapter.supports_schemas()}")
            print(f"  Supports enums: {adapter.supports_enum_types()}")
        except Exception as e:
            print(f"  Error: {e}")
        print()


def test_sql_generation():
    """Test SQL generation."""
    print("\n=== Testing SQL Generation ===\n")
    
    # Create a simple model
    model = (
        ModelBuilder("test_table")
        .add_id_column()
        .add_varchar_column("name", 100, nullable=False)
        .add_boolean_column("active", nullable=False, default=True)
        .build()
    )
    
    # Test SQL generation for each database
    for db_type in [DatabaseType.SQLITE, DatabaseType.POSTGRESQL, DatabaseType.MYSQL]:
        print(f"--- {db_type.value} SQL ---")
        try:
            sql = generate_complete_sql(model, db_type)
            print(sql)
        except Exception as e:
            print(f"Error: {e}")
        print()


def main():
    """Run all tests."""
    test_basic_model()
    test_adapters()
    test_sql_generation()
    print("✅ All tests completed!")


if __name__ == "__main__":
    main() 