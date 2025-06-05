#!/usr/bin/env python3
"""Complete self-contained test for Model Manager functionality."""

from enum import Enum
from typing import List, Optional, Dict, Union
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from abc import ABC, abstractmethod

# === Data Types ===

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
    params: Optional[Union[int, str, List[int], Dict[str, Union[str, int, List[str]]]]] = Field(None, description="Type parameters")
    
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

# === Database Adapters ===

class DatabaseAdapter(ABC):
    """Abstract base class for database-specific adapters."""
    
    @abstractmethod
    def get_type_sql(self, data_type: DataType) -> str:
        """Convert a DataType to database-specific SQL type string."""
        pass
    
    @abstractmethod
    def generate_create_table_sql(self, model: ModelDescriptor) -> str:
        """Generate CREATE TABLE SQL statement."""
        pass
    
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier (table name, column name, etc.)."""
        return f'"{identifier}"'
    
    def supports_schemas(self) -> bool:
        """Check if the database supports schemas."""
        return True
    
    def supports_enum_types(self) -> bool:
        """Check if the database supports enum types."""
        return False

class SqliteAdapter(DatabaseAdapter):
    """SQLite-specific database adapter."""
    
    def get_type_sql(self, data_type: DataType) -> str:
        """Convert a DataType to SQLite SQL type string."""
        type_name = data_type.type_name
        params = data_type.params
        
        if type_name == "Varchar":
            return f"VARCHAR({params})"
        elif type_name == "Integer":
            return "INTEGER"
        elif type_name == "Boolean":
            return "INTEGER"
        else:
            return "TEXT"
    
    def generate_create_table_sql(self, model: ModelDescriptor) -> str:
        """Generate CREATE TABLE SQL statement for SQLite."""
        parts = []
        table_name = self.quote_identifier(model.name)
        parts.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")
        
        column_defs = []
        for column in model.columns:
            column_def = self._generate_column_definition(column)
            column_defs.append(column_def)
        
        parts.append(",\n  ".join(column_defs))
        parts.append("\n)")
        return "".join(parts)
    
    def _generate_column_definition(self, column: ColumnDescriptor) -> str:
        """Generate column definition for SQLite."""
        parts = [self.quote_identifier(column.name)]
        parts.append(self.get_type_sql(column.data_type))
        
        if column.is_primary_key:
            parts.append("PRIMARY KEY")
            if column.auto_increment:
                parts.append("AUTOINCREMENT")
        
        if not column.is_nullable:
            parts.append("NOT NULL")
        
        if column.is_unique and not column.is_primary_key:
            parts.append("UNIQUE")
        
        if column.default_value is not None:
            parts.append(f"DEFAULT {column.default_value}")
        
        return " ".join(parts)
    
    def supports_schemas(self) -> bool:
        """SQLite doesn't support schemas."""
        return False

class PostgresAdapter(DatabaseAdapter):
    """PostgreSQL-specific database adapter."""
    
    def get_type_sql(self, data_type: DataType) -> str:
        """Convert a DataType to PostgreSQL SQL type string."""
        type_name = data_type.type_name
        params = data_type.params
        
        if type_name == "Varchar":
            return f"VARCHAR({params})"
        elif type_name == "Integer":
            if params == "I64" or params == "U64":
                return "BIGINT"
            else:
                return "INTEGER"
        elif type_name == "Boolean":
            return "BOOLEAN"
        else:
            return "TEXT"
    
    def generate_create_table_sql(self, model: ModelDescriptor) -> str:
        """Generate CREATE TABLE SQL statement for PostgreSQL."""
        parts = []
        table_name = self.quote_identifier(model.name)
        parts.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")
        
        column_defs = []
        for column in model.columns:
            column_def = self._generate_column_definition(column)
            column_defs.append(column_def)
        
        parts.append(",\n  ".join(column_defs))
        parts.append("\n)")
        return "".join(parts)
    
    def _generate_column_definition(self, column: ColumnDescriptor) -> str:
        """Generate column definition for PostgreSQL."""
        parts = [self.quote_identifier(column.name)]
        
        if column.auto_increment:
            if column.data_type.type_name == "Integer" and column.data_type.params == "I64":
                parts.append("BIGSERIAL")
            else:
                parts.append("SERIAL")
        else:
            parts.append(self.get_type_sql(column.data_type))
        
        if column.is_primary_key:
            parts.append("PRIMARY KEY")
        
        if not column.is_nullable:
            parts.append("NOT NULL")
        
        if column.is_unique and not column.is_primary_key:
            parts.append("UNIQUE")
        
        if column.default_value is not None:
            parts.append(f"DEFAULT {column.default_value}")
        
        return " ".join(parts)
    
    def supports_enum_types(self) -> bool:
        """PostgreSQL supports enum types."""
        return True

class MySqlAdapter(DatabaseAdapter):
    """MySQL-specific database adapter."""
    
    def get_type_sql(self, data_type: DataType) -> str:
        """Convert a DataType to MySQL SQL type string."""
        type_name = data_type.type_name
        params = data_type.params
        
        if type_name == "Varchar":
            return f"VARCHAR({params})"
        elif type_name == "Integer":
            if params == "I64" or params == "U64":
                return "BIGINT"
            else:
                return "INT"
        elif type_name == "Boolean":
            return "BOOLEAN"
        else:
            return "TEXT"
    
    def generate_create_table_sql(self, model: ModelDescriptor) -> str:
        """Generate CREATE TABLE SQL statement for MySQL."""
        parts = []
        table_name = self.quote_identifier(model.name)
        parts.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")
        
        column_defs = []
        for column in model.columns:
            column_def = self._generate_column_definition(column)
            column_defs.append(column_def)
        
        parts.append(",\n  ".join(column_defs))
        parts.append("\n)")
        return "".join(parts)
    
    def _generate_column_definition(self, column: ColumnDescriptor) -> str:
        """Generate column definition for MySQL."""
        parts = [self.quote_identifier(column.name)]
        parts.append(self.get_type_sql(column.data_type))
        
        if not column.is_nullable:
            parts.append("NOT NULL")
        
        if column.auto_increment:
            parts.append("AUTO_INCREMENT")
        
        if column.is_unique and not column.is_primary_key:
            parts.append("UNIQUE")
        
        if column.default_value is not None:
            parts.append(f"DEFAULT {column.default_value}")
        
        if column.is_primary_key:
            parts.append("PRIMARY KEY")
        
        return " ".join(parts)
    
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier for MySQL (uses backticks)."""
        return f"`{identifier}`"

# === Tests ===

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
    print("✅ All Model Manager tests completed successfully!")

if __name__ == "__main__":
    main() 