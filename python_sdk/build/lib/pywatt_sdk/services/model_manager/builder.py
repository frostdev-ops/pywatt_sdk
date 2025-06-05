"""Builder pattern for creating model descriptors."""

from typing import List, Optional, Dict

from .definitions import (
    ModelDescriptor,
    ColumnDescriptor,
    DataType,
    IntegerSize,
    Constraint,
    IndexDescriptor,
    ReferentialAction,
)
from .errors import ModelDefinitionError


class ModelBuilder:
    """Builder pattern for creating model descriptors.
    
    This provides a fluent API for building complex model definitions
    with validation and sensible defaults.
    """
    
    def __init__(self, table_name: str, schema_name: Optional[str] = None):
        """Create a new model builder.
        
        Args:
            table_name: Name of the table
            schema_name: Optional schema name
        """
        self.model = ModelDescriptor(
            name=table_name,
            schema=schema_name,
            columns=[],
            primary_key=None,
            indexes=[],
            constraints=[],
            comment=None,
            engine=None,
            charset=None,
            collation=None,
            options={},
        )
    
    def add_id_column(self, name: str = "id") -> "ModelBuilder":
        """Add a standard auto-incrementing ID column.
        
        Args:
            name: Column name (default: "id")
            
        Returns:
            Self for method chaining
        """
        self.model.columns.append(ColumnDescriptor(
            name=name,
            data_type=DataType.integer(IntegerSize.I64),
            is_nullable=False,
            is_primary_key=True,
            is_unique=False,
            default_value=None,
            auto_increment=True,
            comment="Primary key",
            constraints=[],
        ))
        return self
    
    def add_varchar_column(
        self,
        name: str,
        length: int,
        nullable: bool = True,
        unique: bool = False,
        default: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add a VARCHAR column.
        
        Args:
            name: Column name
            length: Maximum length
            nullable: Whether the column allows NULL
            unique: Whether the column has a unique constraint
            default: Default value
            comment: Column comment
            
        Returns:
            Self for method chaining
        """
        self.model.columns.append(ColumnDescriptor(
            name=name,
            data_type=DataType.varchar(length),
            is_nullable=nullable,
            is_primary_key=False,
            is_unique=unique,
            default_value=default,
            auto_increment=False,
            comment=comment,
            constraints=[],
        ))
        return self
    
    def add_text_column(
        self,
        name: str,
        nullable: bool = True,
        comment: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add a TEXT column.
        
        Args:
            name: Column name
            nullable: Whether the column allows NULL
            comment: Column comment
            
        Returns:
            Self for method chaining
        """
        self.model.columns.append(ColumnDescriptor(
            name=name,
            data_type=DataType.text(),
            is_nullable=nullable,
            is_primary_key=False,
            is_unique=False,
            default_value=None,
            auto_increment=False,
            comment=comment,
            constraints=[],
        ))
        return self
    
    def add_integer_column(
        self,
        name: str,
        size: IntegerSize = IntegerSize.I32,
        nullable: bool = True,
        unique: bool = False,
        default: Optional[int] = None,
        comment: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add an integer column.
        
        Args:
            name: Column name
            size: Integer size
            nullable: Whether the column allows NULL
            unique: Whether the column has a unique constraint
            default: Default value
            comment: Column comment
            
        Returns:
            Self for method chaining
        """
        self.model.columns.append(ColumnDescriptor(
            name=name,
            data_type=DataType.integer(size),
            is_nullable=nullable,
            is_primary_key=False,
            is_unique=unique,
            default_value=str(default) if default is not None else None,
            auto_increment=False,
            comment=comment,
            constraints=[],
        ))
        return self
    
    def add_boolean_column(
        self,
        name: str,
        nullable: bool = True,
        default: Optional[bool] = None,
        comment: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add a boolean column.
        
        Args:
            name: Column name
            nullable: Whether the column allows NULL
            default: Default value
            comment: Column comment
            
        Returns:
            Self for method chaining
        """
        default_str = None
        if default is not None:
            default_str = "true" if default else "false"
        
        self.model.columns.append(ColumnDescriptor(
            name=name,
            data_type=DataType.boolean(),
            is_nullable=nullable,
            is_primary_key=False,
            is_unique=False,
            default_value=default_str,
            auto_increment=False,
            comment=comment,
            constraints=[],
        ))
        return self
    
    def add_timestamp_column(
        self,
        name: str,
        nullable: bool = True,
        default: Optional[str] = None,
        with_timezone: bool = True,
        comment: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add a timestamp column.
        
        Args:
            name: Column name
            nullable: Whether the column allows NULL
            default: Default value (e.g., "CURRENT_TIMESTAMP")
            with_timezone: Whether to use timezone-aware timestamp
            comment: Column comment
            
        Returns:
            Self for method chaining
        """
        data_type = DataType.timestamp_tz() if with_timezone else DataType.timestamp()
        
        self.model.columns.append(ColumnDescriptor(
            name=name,
            data_type=data_type,
            is_nullable=nullable,
            is_primary_key=False,
            is_unique=False,
            default_value=default,
            auto_increment=False,
            comment=comment,
            constraints=[],
        ))
        return self
    
    def add_json_column(
        self,
        name: str,
        nullable: bool = True,
        binary: bool = False,
        comment: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add a JSON column.
        
        Args:
            name: Column name
            nullable: Whether the column allows NULL
            binary: Whether to use JSONB (PostgreSQL)
            comment: Column comment
            
        Returns:
            Self for method chaining
        """
        data_type = DataType.jsonb() if binary else DataType.json()
        
        self.model.columns.append(ColumnDescriptor(
            name=name,
            data_type=data_type,
            is_nullable=nullable,
            is_primary_key=False,
            is_unique=False,
            default_value=None,
            auto_increment=False,
            comment=comment,
            constraints=[],
        ))
        return self
    
    def add_uuid_column(
        self,
        name: str,
        nullable: bool = True,
        unique: bool = False,
        default: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add a UUID column.
        
        Args:
            name: Column name
            nullable: Whether the column allows NULL
            unique: Whether the column has a unique constraint
            default: Default value (e.g., "gen_random_uuid()")
            comment: Column comment
            
        Returns:
            Self for method chaining
        """
        self.model.columns.append(ColumnDescriptor(
            name=name,
            data_type=DataType.uuid(),
            is_nullable=nullable,
            is_primary_key=False,
            is_unique=unique,
            default_value=default,
            auto_increment=False,
            comment=comment,
            constraints=[],
        ))
        return self
    
    def add_enum_column(
        self,
        name: str,
        enum_name: str,
        values: List[str],
        nullable: bool = True,
        default: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add an enum column.
        
        Args:
            name: Column name
            enum_name: Name of the enum type
            values: List of enum values
            nullable: Whether the column allows NULL
            default: Default value
            comment: Column comment
            
        Returns:
            Self for method chaining
        """
        self.model.columns.append(ColumnDescriptor(
            name=name,
            data_type=DataType.enum(enum_name, values),
            is_nullable=nullable,
            is_primary_key=False,
            is_unique=False,
            default_value=f"'{default}'" if default else None,
            auto_increment=False,
            comment=comment,
            constraints=[],
        ))
        return self
    
    def add_timestamps(self) -> "ModelBuilder":
        """Add created_at and updated_at timestamp columns.
        
        Returns:
            Self for method chaining
        """
        self.add_timestamp_column(
            "created_at",
            nullable=False,
            default="CURRENT_TIMESTAMP",
            comment="Record creation timestamp"
        )
        self.add_timestamp_column(
            "updated_at",
            nullable=False,
            default="CURRENT_TIMESTAMP",
            comment="Record update timestamp"
        )
        return self
    
    def add_index(
        self,
        columns: List[str],
        unique: bool = False,
        name: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add an index.
        
        Args:
            columns: List of column names
            unique: Whether this is a unique index
            name: Optional index name
            
        Returns:
            Self for method chaining
        """
        self.model.indexes.append(IndexDescriptor(
            columns=columns,
            name=name,
            is_unique=unique,
            index_type=None,
            condition=None,
        ))
        return self
    
    def add_foreign_key(
        self,
        columns: List[str],
        references_table: str,
        references_columns: List[str],
        on_delete: Optional[ReferentialAction] = None,
        on_update: Optional[ReferentialAction] = None,
        name: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add a foreign key constraint.
        
        Args:
            columns: List of column names in this table
            references_table: Referenced table name
            references_columns: List of column names in referenced table
            on_delete: Action on delete
            on_update: Action on update
            name: Optional constraint name
            
        Returns:
            Self for method chaining
        """
        self.model.constraints.append(Constraint.foreign_key(
            columns=columns,
            references_table=references_table,
            references_columns=references_columns,
            name=name,
            on_delete=on_delete,
            on_update=on_update,
        ))
        return self
    
    def add_unique_constraint(
        self,
        columns: List[str],
        name: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add a unique constraint.
        
        Args:
            columns: List of column names
            name: Optional constraint name
            
        Returns:
            Self for method chaining
        """
        self.model.constraints.append(Constraint.unique(
            name=name,
            columns=columns,
        ))
        return self
    
    def add_check_constraint(
        self,
        expression: str,
        name: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add a check constraint.
        
        Args:
            expression: Check expression
            name: Optional constraint name
            
        Returns:
            Self for method chaining
        """
        self.model.constraints.append(Constraint.check(
            expression=expression,
            name=name,
        ))
        return self
    
    def with_comment(self, comment: str) -> "ModelBuilder":
        """Set table comment.
        
        Args:
            comment: Table comment
            
        Returns:
            Self for method chaining
        """
        self.model.comment = comment
        return self
    
    def with_engine(self, engine: str) -> "ModelBuilder":
        """Set storage engine (MySQL).
        
        Args:
            engine: Storage engine (e.g., "InnoDB")
            
        Returns:
            Self for method chaining
        """
        self.model.engine = engine
        return self
    
    def with_charset(self, charset: str) -> "ModelBuilder":
        """Set character set (MySQL).
        
        Args:
            charset: Character set (e.g., "utf8mb4")
            
        Returns:
            Self for method chaining
        """
        self.model.charset = charset
        return self
    
    def with_collation(self, collation: str) -> "ModelBuilder":
        """Set collation (MySQL).
        
        Args:
            collation: Collation (e.g., "utf8mb4_unicode_ci")
            
        Returns:
            Self for method chaining
        """
        self.model.collation = collation
        return self
    
    def with_option(self, key: str, value: str) -> "ModelBuilder":
        """Add a custom option.
        
        Args:
            key: Option key
            value: Option value
            
        Returns:
            Self for method chaining
        """
        self.model.options[key] = value
        return self
    
    def build(self) -> ModelDescriptor:
        """Build the model descriptor.
        
        Returns:
            The completed model descriptor
        """
        return self.model
    
    def build_validated(self) -> ModelDescriptor:
        """Build and validate the model descriptor.
        
        Returns:
            The validated model descriptor
            
        Raises:
            ModelDefinitionError: If validation fails
        """
        from .api import validate_model
        
        model = self.build()
        validate_model(model)
        return model 