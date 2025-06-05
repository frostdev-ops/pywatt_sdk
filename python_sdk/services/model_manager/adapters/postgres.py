"""PostgreSQL database adapter."""

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


class PostgresAdapter(DatabaseAdapter):
    """PostgreSQL-specific database adapter."""
    
    def get_type_sql(self, data_type: DataType) -> str:
        """Convert a DataType to PostgreSQL SQL type string."""
        type_name = data_type.type_name
        params = data_type.params
        
        if type_name == "Text":
            if params:
                return f"VARCHAR({params})"
            return "TEXT"
        elif type_name == "Varchar":
            return f"VARCHAR({params})"
        elif type_name == "Char":
            return f"CHAR({params})"
        elif type_name == "Integer":
            if params == "I8" or params == "U8":
                return "SMALLINT"  # PostgreSQL doesn't have TINYINT
            elif params == "I16" or params == "U16":
                return "SMALLINT"
            elif params == "I32" or params == "U32":
                return "INTEGER"
            elif params == "I64" or params == "U64":
                return "BIGINT"
            else:
                return "INTEGER"
        elif type_name == "SmallInt":
            return "SMALLINT"
        elif type_name == "BigInt":
            return "BIGINT"
        elif type_name == "Boolean":
            return "BOOLEAN"
        elif type_name == "Float":
            return "REAL"
        elif type_name == "Double":
            return "DOUBLE PRECISION"
        elif type_name == "Decimal":
            if isinstance(params, list) and len(params) == 2:
                return f"DECIMAL({params[0]},{params[1]})"
            return "DECIMAL"
        elif type_name == "Date":
            return "DATE"
        elif type_name == "Time":
            return "TIME"
        elif type_name == "DateTime":
            return "TIMESTAMP"
        elif type_name == "Timestamp":
            return "TIMESTAMP"
        elif type_name == "TimestampTz":
            return "TIMESTAMP WITH TIME ZONE"
        elif type_name == "Blob":
            return "BYTEA"
        elif type_name == "Json":
            return "JSON"
        elif type_name == "JsonB":
            return "JSONB"
        elif type_name == "Uuid":
            return "UUID"
        elif type_name == "Enum":
            if isinstance(params, dict) and "name" in params:
                return params["name"]
            raise DatabaseAdapterError("Enum type requires name parameter")
        elif type_name == "Custom":
            return str(params)
        else:
            raise DatabaseAdapterError(f"Unsupported data type: {type_name}")
    
    def generate_create_table_sql(self, model: ModelDescriptor) -> str:
        """Generate CREATE TABLE SQL statement for PostgreSQL."""
        parts = []
        
        # Table name with schema
        table_name = self.get_qualified_table_name(model.name, model.schema)
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
        
        # Table comment
        sql = "".join(parts)
        if model.comment:
            sql += f";\nCOMMENT ON TABLE {table_name} IS '{model.comment}'"
        
        return sql
    
    def _generate_column_definition(self, column: ColumnDescriptor) -> str:
        """Generate column definition for PostgreSQL."""
        parts = [self.quote_identifier(column.name)]
        
        # Handle auto-increment with SERIAL types
        if column.auto_increment:
            if column.data_type.type_name == "SmallInt":
                parts.append("SMALLSERIAL")
            elif column.data_type.type_name == "BigInt":
                parts.append("BIGSERIAL")
            else:
                parts.append("SERIAL")
        else:
            parts.append(self.get_type_sql(column.data_type))
        
        # Handle constraints
        if column.is_primary_key:
            parts.append("PRIMARY KEY")
        
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
        """Generate foreign key constraint for PostgreSQL."""
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
        """Generate DROP TABLE SQL statement for PostgreSQL."""
        table = self.get_qualified_table_name(table_name, schema)
        if if_exists:
            return f"DROP TABLE IF EXISTS {table} CASCADE"
        return f"DROP TABLE {table} CASCADE"
    
    def generate_create_index_sql(self, table_name: str, index: IndexDescriptor, schema: Optional[str] = None) -> str:
        """Generate CREATE INDEX SQL statement for PostgreSQL."""
        # Generate index name if not provided
        if index.name:
            index_name = self.quote_identifier(index.name)
        else:
            cols_str = "_".join(index.columns)
            index_name = self.quote_identifier(f"idx_{table_name}_{cols_str}")
        
        table = self.get_qualified_table_name(table_name, schema)
        columns = ", ".join(self.quote_identifier(col) for col in index.columns)
        
        parts = []
        if index.is_unique:
            parts.append("CREATE UNIQUE INDEX")
        else:
            parts.append("CREATE INDEX")
        
        if self.supports_if_not_exists():
            parts.append("IF NOT EXISTS")
        
        parts.append(index_name)
        parts.append(f"ON {table}")
        
        # Index type
        if index.index_type:
            if index.index_type == IndexType.BTREE:
                parts.append("USING BTREE")
            elif index.index_type == IndexType.HASH:
                parts.append("USING HASH")
            elif index.index_type == IndexType.GIN:
                parts.append("USING GIN")
            elif index.index_type == IndexType.GIST:
                parts.append("USING GIST")
        
        parts.append(f"({columns})")
        
        if index.condition:
            parts.append(f"WHERE {index.condition}")
        
        return " ".join(parts)
    
    def generate_add_column_sql(self, table_name: str, column: ColumnDescriptor, schema: Optional[str] = None) -> str:
        """Generate ALTER TABLE ADD COLUMN SQL statement for PostgreSQL."""
        table = self.get_qualified_table_name(table_name, schema)
        column_def = self._generate_column_definition(column)
        
        return f"ALTER TABLE {table} ADD COLUMN {column_def}"
    
    def generate_drop_column_sql(self, table_name: str, column_name: str, schema: Optional[str] = None) -> str:
        """Generate ALTER TABLE DROP COLUMN SQL statement for PostgreSQL."""
        table = self.get_qualified_table_name(table_name, schema)
        column = self.quote_identifier(column_name)
        
        return f"ALTER TABLE {table} DROP COLUMN {column}"
    
    def generate_enum_types_sql(self, model: ModelDescriptor) -> List[str]:
        """Generate SQL statements for creating enum types in PostgreSQL."""
        enum_statements = []
        
        for column in model.columns:
            if column.data_type.type_name == "Enum":
                params = column.data_type.params
                if isinstance(params, dict) and "name" in params and "values" in params:
                    enum_name = params["name"]
                    values = params["values"]
                    
                    # Create enum type
                    values_sql = ", ".join(f"'{value}'" for value in values)
                    enum_sql = f"CREATE TYPE {self.quote_identifier(enum_name)} AS ENUM ({values_sql})"
                    enum_statements.append(enum_sql)
        
        return enum_statements
    
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier for PostgreSQL (uses double quotes)."""
        return f'"{identifier}"'
    
    def supports_enum_types(self) -> bool:
        """PostgreSQL supports enum types."""
        return True
    
    def get_current_timestamp_sql(self) -> str:
        """Get the SQL expression for current timestamp in PostgreSQL."""
        return "CURRENT_TIMESTAMP" 