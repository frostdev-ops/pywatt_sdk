"""SQLite database adapter."""

from typing import List, Optional

from .base import DatabaseAdapter
from ..definitions import (
    ModelDescriptor,
    ColumnDescriptor,
    DataType,
    IntegerSize,
    Constraint,
    IndexDescriptor,
    IndexType,
    PrimaryKeyConstraint,
    UniqueConstraint,
    NotNullConstraint,
    DefaultValueConstraint,
    CheckConstraint,
    ForeignKeyConstraint,
    AutoIncrementConstraint,
)
from ..errors import DatabaseAdapterError, UnsupportedFeatureError


class SqliteAdapter(DatabaseAdapter):
    """SQLite-specific database adapter."""
    
    def get_type_sql(self, data_type: DataType) -> str:
        """Convert a DataType to SQLite SQL type string."""
        type_name = data_type.type_name
        params = data_type.params
        
        if type_name == "Text":
            return "TEXT"
        elif type_name == "Varchar":
            return f"VARCHAR({params})"
        elif type_name == "Char":
            return f"CHAR({params})"
        elif type_name == "Integer":
            # SQLite uses INTEGER for all integer types
            return "INTEGER"
        elif type_name == "SmallInt":
            return "INTEGER"
        elif type_name == "BigInt":
            return "INTEGER"
        elif type_name == "Boolean":
            # SQLite doesn't have a boolean type, use INTEGER
            return "INTEGER"
        elif type_name == "Float":
            return "REAL"
        elif type_name == "Double":
            return "REAL"
        elif type_name == "Decimal":
            if isinstance(params, list) and len(params) == 2:
                return f"DECIMAL({params[0]},{params[1]})"
            return "DECIMAL"
        elif type_name == "Date":
            return "DATE"
        elif type_name == "Time":
            return "TIME"
        elif type_name == "DateTime":
            return "DATETIME"
        elif type_name == "Timestamp":
            return "TIMESTAMP"
        elif type_name == "TimestampTz":
            # SQLite doesn't have timezone support
            return "TIMESTAMP"
        elif type_name == "Blob":
            return "BLOB"
        elif type_name == "Json":
            # SQLite stores JSON as TEXT
            return "TEXT"
        elif type_name == "JsonB":
            # SQLite doesn't have JSONB
            return "TEXT"
        elif type_name == "Uuid":
            # SQLite doesn't have UUID type
            return "TEXT"
        elif type_name == "Enum":
            # SQLite doesn't have enum types
            return "TEXT"
        elif type_name == "Custom":
            return str(params)
        else:
            raise DatabaseAdapterError(f"Unsupported data type: {type_name}")
    
    def generate_create_table_sql(self, model: ModelDescriptor) -> str:
        """Generate CREATE TABLE SQL statement for SQLite."""
        parts = []
        
        # Table name
        table_name = self.quote_identifier(model.name)
        if self.supports_if_not_exists():
            parts.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")
        else:
            parts.append(f"CREATE TABLE {table_name} (")
        
        # Columns
        column_defs = []
        for column in model.columns:
            column_def = self._generate_column_definition(column)
            column_defs.append(column_def)
        
        # Table-level primary key
        if model.primary_key:
            pk_columns = ", ".join(self.quote_identifier(col) for col in model.primary_key)
            column_defs.append(f"PRIMARY KEY ({pk_columns})")
        
        # Table-level constraints
        for constraint in model.constraints:
            if isinstance(constraint, UniqueConstraint):
                cols = ", ".join(self.quote_identifier(col) for col in constraint.columns)
                if constraint.name:
                    column_defs.append(f"CONSTRAINT {self.quote_identifier(constraint.name)} UNIQUE ({cols})")
                else:
                    column_defs.append(f"UNIQUE ({cols})")
            elif isinstance(constraint, CheckConstraint):
                if constraint.name:
                    column_defs.append(f"CONSTRAINT {self.quote_identifier(constraint.name)} CHECK ({constraint.expression})")
                else:
                    column_defs.append(f"CHECK ({constraint.expression})")
            elif isinstance(constraint, ForeignKeyConstraint):
                fk_sql = self._generate_foreign_key_constraint(constraint)
                column_defs.append(fk_sql)
        
        parts.append(",\n  ".join(column_defs))
        parts.append("\n)")
        
        return "".join(parts)
    
    def _generate_column_definition(self, column: ColumnDescriptor) -> str:
        """Generate column definition for SQLite."""
        parts = [self.quote_identifier(column.name)]
        parts.append(self.get_type_sql(column.data_type))
        
        # Handle constraints
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
        
        # Column-level constraints
        for constraint in column.constraints:
            if isinstance(constraint, CheckConstraint):
                parts.append(f"CHECK ({constraint.expression})")
        
        return " ".join(parts)
    
    def _generate_foreign_key_constraint(self, constraint: ForeignKeyConstraint) -> str:
        """Generate foreign key constraint for SQLite."""
        parts = []
        
        if constraint.name:
            parts.append(f"CONSTRAINT {self.quote_identifier(constraint.name)}")
        
        cols = ", ".join(self.quote_identifier(col) for col in constraint.columns)
        ref_cols = ", ".join(self.quote_identifier(col) for col in constraint.references_columns)
        
        parts.append(f"FOREIGN KEY ({cols})")
        parts.append(f"REFERENCES {self.quote_identifier(constraint.references_table)} ({ref_cols})")
        
        if constraint.on_delete:
            parts.append(f"ON DELETE {self.get_referential_action_sql(constraint.on_delete)}")
        
        if constraint.on_update:
            parts.append(f"ON UPDATE {self.get_referential_action_sql(constraint.on_update)}")
        
        return " ".join(parts)
    
    def generate_drop_table_sql(self, table_name: str, schema: Optional[str] = None, if_exists: bool = True) -> str:
        """Generate DROP TABLE SQL statement for SQLite."""
        if schema:
            raise UnsupportedFeatureError("SQLite does not support schemas")
        
        table = self.quote_identifier(table_name)
        if if_exists:
            return f"DROP TABLE IF EXISTS {table}"
        return f"DROP TABLE {table}"
    
    def generate_create_index_sql(self, table_name: str, index: IndexDescriptor, schema: Optional[str] = None) -> str:
        """Generate CREATE INDEX SQL statement for SQLite."""
        if schema:
            raise UnsupportedFeatureError("SQLite does not support schemas")
        
        # Generate index name if not provided
        if index.name:
            index_name = self.quote_identifier(index.name)
        else:
            cols_str = "_".join(index.columns)
            index_name = self.quote_identifier(f"idx_{table_name}_{cols_str}")
        
        table = self.quote_identifier(table_name)
        columns = ", ".join(self.quote_identifier(col) for col in index.columns)
        
        parts = []
        if index.is_unique:
            parts.append("CREATE UNIQUE INDEX")
        else:
            parts.append("CREATE INDEX")
        
        if self.supports_if_not_exists():
            parts.append("IF NOT EXISTS")
        
        parts.append(index_name)
        parts.append(f"ON {table} ({columns})")
        
        if index.condition:
            parts.append(f"WHERE {index.condition}")
        
        return " ".join(parts)
    
    def generate_add_column_sql(self, table_name: str, column: ColumnDescriptor, schema: Optional[str] = None) -> str:
        """Generate ALTER TABLE ADD COLUMN SQL statement for SQLite."""
        if schema:
            raise UnsupportedFeatureError("SQLite does not support schemas")
        
        table = self.quote_identifier(table_name)
        column_def = self._generate_column_definition(column)
        
        return f"ALTER TABLE {table} ADD COLUMN {column_def}"
    
    def generate_drop_column_sql(self, table_name: str, column_name: str, schema: Optional[str] = None) -> str:
        """Generate ALTER TABLE DROP COLUMN SQL statement for SQLite."""
        if schema:
            raise UnsupportedFeatureError("SQLite does not support schemas")
        
        # SQLite doesn't support DROP COLUMN directly
        raise UnsupportedFeatureError("SQLite does not support DROP COLUMN. You need to recreate the table.")
    
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier for SQLite (uses double quotes)."""
        return f'"{identifier}"'
    
    def supports_schemas(self) -> bool:
        """SQLite doesn't support schemas."""
        return False
    
    def get_auto_increment_sql(self) -> str:
        """Get the SQL keyword for auto-increment columns in SQLite."""
        return "AUTOINCREMENT" 