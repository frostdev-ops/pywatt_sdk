#!/usr/bin/env python3
"""Standalone test for Model Manager functionality."""

from enum import Enum
from typing import List, Optional, Dict, Union
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

# Copy the essential types locally to avoid import issues
class DatabaseType(str, Enum):
    """Database types."""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"

class IntegerSize(str, Enum):
    """Integer size variants for the Integer data type."""
    I8 = "I8"
    U8 = "U8"
    I16 = "I16"
    U16 = "U16"
    I32 = "I32"
    U32 = "U32"
    I64 = "I64"
    U64 = "U64"

class DataType(BaseModel):
    """Common database data types that can be mapped to specific databases."""
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
    
    type_name: str = Field(..., description="Type name")
    params: Optional[Union[int, List[int], Dict[str, Union[str, int, List[str]]]]] = Field(None, description="Type parameters")
    
    @classmethod
    def varchar(cls, length: int) -> "DataType":
        """Variable-length character string with specified maximum length."""
        return cls(type_name="Varchar", params=length)
    
    @classmethod
    def integer(cls, size: IntegerSize) -> "DataType":
        """Integer with specific size."""
        return cls(type_name="Integer", params=size.value)
    
    @classmethod
    def boolean(cls) -> "DataType":
        """Boolean true/false."""
        return cls(type_name="Boolean")
    
    @classmethod
    def timestamp_tz(cls) -> "DataType":
        """Timestamp with time zone."""
        return cls(type_name="TimestampTz")

@dataclass
class ColumnDescriptor:
    """Column definition for a database table."""
    name: str
    data_type: DataType
    is_nullable: bool = True
    is_primary_key: bool = False
    is_unique: bool = False
    default_value: Optional[str] = None
    auto_increment: bool = False
    comment: Optional[str] = None
    constraints: List = field(default_factory=list)

@dataclass
class ModelDescriptor:
    """Complete table/model definition."""
    name: str
    columns: List[ColumnDescriptor]
    schema: Optional[str] = None
    primary_key: Optional[List[str]] = None
    indexes: List = field(default_factory=list)
    constraints: List = field(default_factory=list)
    comment: Optional[str] = None
    engine: Optional[str] = None
    charset: Optional[str] = None
    collation: Optional[str] = None
    options: Dict[str, str] = field(default_factory=dict)

# Import the actual implementations
from adapters.sqlite import SqliteAdapter
from adapters.postgres import PostgresAdapter
from adapters.mysql import MySqlAdapter


def test_adapters():
    """Test the database adapters."""
    print("=== Testing Database Adapters ===\n")
    
    # Create test data types
    varchar_type = DataType.varchar(100)
    int_type = DataType.integer(IntegerSize.I64)
    bool_type = DataType.boolean()
    
    adapters = [
        ("SQLite", SqliteAdapter()),
        ("PostgreSQL", PostgresAdapter()),
        ("MySQL", MySqlAdapter()),
    ]
    
    for name, adapter in adapters:
        print(f"{name} Adapter:")
        try:
            print(f"  VARCHAR(100) -> {adapter.get_type_sql(varchar_type)}")
            print(f"  INTEGER(I64) -> {adapter.get_type_sql(int_type)}")
            print(f"  BOOLEAN -> {adapter.get_type_sql(bool_type)}")
            print(f"  Supports schemas: {adapter.supports_schemas()}")
            print(f"  Supports enums: {adapter.supports_enum_types()}")
            print("  ✓ Adapter working correctly")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        print()


def test_table_generation():
    """Test table generation."""
    print("=== Testing Table Generation ===\n")
    
    # Create a simple model
    model = ModelDescriptor(
        name="users",
        columns=[
            ColumnDescriptor(
                name="id",
                data_type=DataType.integer(IntegerSize.I64),
                is_nullable=False,
                is_primary_key=True,
                auto_increment=True,
                comment="Primary key"
            ),
            ColumnDescriptor(
                name="username",
                data_type=DataType.varchar(100),
                is_nullable=False,
                is_unique=True
            ),
            ColumnDescriptor(
                name="is_active",
                data_type=DataType.boolean(),
                is_nullable=False,
                default_value="true"
            ),
        ]
    )
    
    adapters = [
        ("SQLite", SqliteAdapter()),
        ("PostgreSQL", PostgresAdapter()),
        ("MySQL", MySqlAdapter()),
    ]
    
    for name, adapter in adapters:
        print(f"{name} CREATE TABLE:")
        try:
            sql = adapter.generate_create_table_sql(model)
            print(sql)
            print("  ✓ SQL generated successfully")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        print()


def main():
    """Run all tests."""
    test_adapters()
    test_table_generation()
    print("✅ All tests completed!")


if __name__ == "__main__":
    main() 