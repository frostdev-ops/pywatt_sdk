#!/usr/bin/env python3
"""Test the PyWatt Model Manager functionality."""

import asyncio
from typing import Optional

# Import Model Manager components directly
from services.model_manager import (
    ModelBuilder,
    DataType,
    IntegerSize,
    ReferentialAction,
    create_simple_model,
    validate_model,
    generate_complete_sql,
)
from data.database import DatabaseType


def test_model_builder():
    """Test the model builder functionality."""
    print("=== Testing Model Builder ===\n")
    
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


def test_sql_generation(model):
    """Test SQL generation for different databases."""
    print("\n\n=== Testing SQL Generation ===")
    
    for db_type in [DatabaseType.SQLITE, DatabaseType.POSTGRESQL, DatabaseType.MYSQL]:
        print(f"\n--- {db_type.value} SQL ---")
        try:
            sql = generate_complete_sql(model, db_type)
            print(sql)
        except Exception as e:
            print(f"Error: {e}")


def test_complex_model():
    """Test a more complex model with relationships."""
    print("\n\n=== Testing Complex Model ===\n")
    
    # Create a blog post model
    model = (
        ModelBuilder("posts")
        .add_id_column()
        .add_varchar_column("title", 200, nullable=False)
        .add_text_column("content", nullable=False)
        .add_integer_column("author_id", IntegerSize.I64, nullable=False)
        .add_json_column("metadata", nullable=True)
        .add_timestamps()
        .add_foreign_key(
            ["author_id"],
            "users",
            ["id"],
            on_delete=ReferentialAction.CASCADE
        )
        .add_index(["author_id"])
        .add_index(["created_at"])
        .build()
    )
    
    print(f"Created model: {model.name}")
    print(f"Columns: {len(model.columns)}")
    print(f"Indexes: {len(model.indexes)}")
    print(f"Constraints: {len(model.constraints)}")
    
    # Generate PostgreSQL SQL
    print("\nPostgreSQL SQL:")
    sql = generate_complete_sql(model, DatabaseType.POSTGRESQL)
    print(sql)


def main():
    """Run all tests."""
    # Test basic model builder
    model = test_model_builder()
    
    # Test SQL generation
    test_sql_generation(model)
    
    # Test complex model
    test_complex_model()
    
    print("\n\n✅ All tests completed!")


if __name__ == "__main__":
    main() 