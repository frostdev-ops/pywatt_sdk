"""Data type definitions for the Model Manager.

This module defines the core data structures used for database model definitions,
including data types, constraints, and descriptors.
"""

from enum import Enum
from typing import List, Optional, Dict, Union
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


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
    def text(cls, length: Optional[int] = None) -> "DataType":
        """Text with optional length."""
        return cls(type_name="Text", params=length)
    
    @classmethod
    def varchar(cls, length: int) -> "DataType":
        """Variable-length character string with specified maximum length."""
        return cls(type_name="Varchar", params=length)
    
    @classmethod
    def char(cls, length: int) -> "DataType":
        """Fixed-length character string."""
        return cls(type_name="Char", params=length)
    
    @classmethod
    def integer(cls, size: IntegerSize) -> "DataType":
        """Integer with specific size."""
        return cls(type_name="Integer", params=size.value)
    
    @classmethod
    def small_int(cls) -> "DataType":
        """Small integer (typically 16-bit)."""
        return cls(type_name="SmallInt")
    
    @classmethod
    def big_int(cls) -> "DataType":
        """Big integer (typically 64-bit)."""
        return cls(type_name="BigInt")
    
    @classmethod
    def boolean(cls) -> "DataType":
        """Boolean true/false."""
        return cls(type_name="Boolean")
    
    @classmethod
    def float(cls) -> "DataType":
        """Single-precision floating point."""
        return cls(type_name="Float")
    
    @classmethod
    def double(cls) -> "DataType":
        """Double-precision floating point."""
        return cls(type_name="Double")
    
    @classmethod
    def decimal(cls, precision: int, scale: int) -> "DataType":
        """Decimal number with specified precision and scale."""
        return cls(type_name="Decimal", params=[precision, scale])
    
    @classmethod
    def date(cls) -> "DataType":
        """Date (without time)."""
        return cls(type_name="Date")
    
    @classmethod
    def time(cls) -> "DataType":
        """Time (without date)."""
        return cls(type_name="Time")
    
    @classmethod
    def datetime(cls) -> "DataType":
        """Date and time."""
        return cls(type_name="DateTime")
    
    @classmethod
    def timestamp(cls) -> "DataType":
        """Timestamp (often with time zone)."""
        return cls(type_name="Timestamp")
    
    @classmethod
    def timestamp_tz(cls) -> "DataType":
        """Timestamp with time zone."""
        return cls(type_name="TimestampTz")
    
    @classmethod
    def blob(cls) -> "DataType":
        """Binary large object."""
        return cls(type_name="Blob")
    
    @classmethod
    def json(cls) -> "DataType":
        """JSON data."""
        return cls(type_name="Json")
    
    @classmethod
    def jsonb(cls) -> "DataType":
        """PostgreSQL's binary JSON."""
        return cls(type_name="JsonB")
    
    @classmethod
    def uuid(cls) -> "DataType":
        """UUID."""
        return cls(type_name="Uuid")
    
    @classmethod
    def enum(cls, name: str, values: List[str]) -> "DataType":
        """Enumeration type with name and allowed values."""
        return cls(type_name="Enum", params={"name": name, "values": values})
    
    @classmethod
    def custom(cls, type_str: str) -> "DataType":
        """Custom or database-specific type."""
        return cls(type_name="Custom", params=type_str)


class ReferentialAction(str, Enum):
    """Actions to take on foreign key references."""
    NO_ACTION = "NoAction"
    RESTRICT = "Restrict"
    CASCADE = "Cascade"
    SET_NULL = "SetNull"
    SET_DEFAULT = "SetDefault"


@dataclass
class Constraint:
    """Database constraints for columns or tables."""
    
    @classmethod
    def primary_key(cls, name: Optional[str] = None, columns: Optional[List[str]] = None) -> "Constraint":
        """Primary key constraint."""
        return PrimaryKeyConstraint(name=name, columns=columns or [])
    
    @classmethod
    def unique(cls, name: Optional[str] = None, columns: Optional[List[str]] = None) -> "Constraint":
        """Unique constraint."""
        return UniqueConstraint(name=name, columns=columns or [])
    
    @classmethod
    def not_null(cls) -> "Constraint":
        """Not null constraint."""
        return NotNullConstraint()
    
    @classmethod
    def default_value(cls, value: str) -> "Constraint":
        """Default value constraint."""
        return DefaultValueConstraint(value=value)
    
    @classmethod
    def check(cls, expression: str, name: Optional[str] = None) -> "Constraint":
        """Check constraint."""
        return CheckConstraint(name=name, expression=expression)
    
    @classmethod
    def foreign_key(
        cls,
        columns: List[str],
        references_table: str,
        references_columns: List[str],
        name: Optional[str] = None,
        on_delete: Optional[ReferentialAction] = None,
        on_update: Optional[ReferentialAction] = None,
    ) -> "Constraint":
        """Foreign key constraint."""
        return ForeignKeyConstraint(
            name=name,
            columns=columns,
            references_table=references_table,
            references_columns=references_columns,
            on_delete=on_delete,
            on_update=on_update,
        )
    
    @classmethod
    def auto_increment(cls) -> "Constraint":
        """Auto-increment constraint."""
        return AutoIncrementConstraint()


@dataclass
class PrimaryKeyConstraint(Constraint):
    """Primary key constraint."""
    name: Optional[str] = None
    columns: List[str] = field(default_factory=list)


@dataclass
class UniqueConstraint(Constraint):
    """Unique constraint."""
    name: Optional[str] = None
    columns: List[str] = field(default_factory=list)


@dataclass
class NotNullConstraint(Constraint):
    """Not null constraint."""
    pass


@dataclass
class DefaultValueConstraint(Constraint):
    """Default value constraint."""
    value: str = ""


@dataclass
class CheckConstraint(Constraint):
    """Check constraint."""
    name: Optional[str] = None
    expression: str = ""


@dataclass
class ForeignKeyConstraint(Constraint):
    """Foreign key constraint."""
    name: Optional[str] = None
    columns: List[str] = field(default_factory=list)
    references_table: str = ""
    references_columns: List[str] = field(default_factory=list)
    on_delete: Optional[ReferentialAction] = None
    on_update: Optional[ReferentialAction] = None


@dataclass
class AutoIncrementConstraint(Constraint):
    """Auto-increment constraint."""
    pass


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
    constraints: List[Constraint] = field(default_factory=list)


class IndexType(str, Enum):
    """Index types for different database engines."""
    BTREE = "BTree"
    HASH = "Hash"
    GIN = "Gin"  # PostgreSQL GIN index
    GIST = "Gist"  # PostgreSQL GiST index
    SPATIAL = "Spatial"


@dataclass
class IndexDescriptor:
    """Index definition for a database table."""
    columns: List[str]
    name: Optional[str] = None
    is_unique: bool = False
    index_type: Optional[IndexType] = None
    condition: Optional[str] = None  # For partial indexes


@dataclass
class ModelDescriptor:
    """Complete table/model definition."""
    name: str
    columns: List[ColumnDescriptor]
    schema: Optional[str] = None
    primary_key: Optional[List[str]] = None
    indexes: List[IndexDescriptor] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)
    comment: Optional[str] = None
    engine: Optional[str] = None  # Storage engine (e.g., "InnoDB" for MySQL)
    charset: Optional[str] = None  # Character set (e.g., "utf8mb4" for MySQL)
    collation: Optional[str] = None  # Collation (e.g., "utf8mb4_unicode_ci" for MySQL)
    options: Dict[str, str] = field(default_factory=dict)  # Additional database-specific options 