"""MySQL database adapter."""

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


class MySqlAdapter(DatabaseAdapter):
    """MySQL-specific database adapter."""
    
    def get_type_sql(self, data_type: DataType) -> str:
        """Convert a DataType to MySQL SQL type string."""
        type_name = data_type.type_name
        params = data_type.params
        
        if type_name == "Text":
            if params and params <= 65535:
                return "TEXT"
            elif params and params <= 16777215:
                return "MEDIUMTEXT"
            else:
                return "LONGTEXT"
        elif type_name == "Varchar":
            return f"VARCHAR({params})"
        elif type_name == "Char":
            return f"CHAR({params})"
        elif type_name == "Integer":
            if params == "I8":
                return "TINYINT"
            elif params == "U8":
                return "TINYINT UNSIGNED"
            elif params == "I16":
                return "SMALLINT"
            elif params == "U16":
                return "SMALLINT UNSIGNED"
            elif params == "I32":
                return "INT"
            elif params == "U32":
                return "INT UNSIGNED"
            elif params == "I64":
                return "BIGINT"
            elif params == "U64":
                return "BIGINT UNSIGNED"
            else:
                return "INT"
        elif type_name == "SmallInt":
            return "SMALLINT"
        elif type_name == "BigInt":
            return "BIGINT"
        elif type_name == "Boolean":
            return "BOOLEAN"  # MySQL treats this as TINYINT(1)
        elif type_name == "Float":
            return "FLOAT"
        elif type_name == "Double":
            return "DOUBLE"
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
            # MySQL doesn't have timezone-aware timestamps
            return "TIMESTAMP"
        elif type_name == "Blob":
            return "BLOB"
        elif type_name == "Json":
            return "JSON"
        elif type_name == "JsonB":
            # MySQL doesn't have JSONB, use JSON
            return "JSON"
        elif type_name == "Uuid":
            # MySQL doesn't have UUID type, use CHAR(36)
            return "CHAR(36)"
        elif type_name == "Enum":
            if isinstance(params, dict) and "values" in params:
                values = params["values"]
                values_sql = ", ".join(f"'{value}'" for value in values)
                return f"ENUM({values_sql})"
            raise DatabaseAdapterError("Enum type requires values parameter")
        elif type_name == "Custom":
            return str(params)
        else:
            raise DatabaseAdapterError(f"Unsupported data type: {type_name}")
    
    def generate_create_table_sql(self, model: ModelDescriptor) -> str:
        """Generate CREATE TABLE SQL statement for MySQL."""
        parts = []
        
        # Table name with schema (database)
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
                # MySQL 8.0.16+ supports CHECK constraints
                if constraint.name:
                    column_defs.append(f"CONSTRAINT {self.quote_identifier(constraint.name)} CHECK ({constraint.expression})")
                else:
                    column_defs.append(f"CHECK ({constraint.expression})")
            elif isinstance(constraint, ForeignKeyConstraint):
                fk_sql = self._generate_foreign_key_constraint(constraint)
                column_defs.append(fk_sql)
        
        parts.append(",\n  ".join(column_defs))
        parts.append("\n)")
        
        # Table options
        options = []
        if model.engine:
            options.append(f"ENGINE={model.engine}")
        if model.charset:
            options.append(f"DEFAULT CHARSET={model.charset}")
        if model.collation:
            options.append(f"COLLATE={model.collation}")
        if model.comment:
            options.append(f"COMMENT='{model.comment}'")
        
        if options:
            parts.append(" ")
            parts.append(" ".join(options))
        
        return "".join(parts)
    
    def _generate_column_definition(self, column: ColumnDescriptor) -> str:
        """Generate column definition for MySQL."""
        parts = [self.quote_identifier(column.name)]
        parts.append(self.get_type_sql(column.data_type))
        
        # Handle constraints
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
        
        if column.comment:
            parts.append(f"COMMENT '{column.comment}'")
        
        # Column-level constraints
        for constraint in column.constraints:
            if isinstance(constraint, CheckConstraint):
                parts.append(f"CHECK ({constraint.expression})")
        
        return " ".join(parts)
    
    def _generate_foreign_key_constraint(self, constraint: ForeignKeyConstraint) -> str:
        """Generate foreign key constraint for MySQL."""
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
        """Generate DROP TABLE SQL statement for MySQL."""
        table = self.get_qualified_table_name(table_name, schema)
        if if_exists:
            return f"DROP TABLE IF EXISTS {table}"
        return f"DROP TABLE {table}"
    
    def generate_create_index_sql(self, table_name: str, index: IndexDescriptor, schema: Optional[str] = None) -> str:
        """Generate CREATE INDEX SQL statement for MySQL."""
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
        
        parts.append(index_name)
        parts.append(f"ON {table} ({columns})")
        
        # Index type
        if index.index_type:
            if index.index_type == IndexType.BTREE:
                parts.append("USING BTREE")
            elif index.index_type == IndexType.HASH:
                parts.append("USING HASH")
            elif index.index_type == IndexType.SPATIAL:
                # For spatial indexes
                parts = ["CREATE SPATIAL INDEX", index_name, f"ON {table} ({columns})"]
        
        return " ".join(parts)
    
    def generate_add_column_sql(self, table_name: str, column: ColumnDescriptor, schema: Optional[str] = None) -> str:
        """Generate ALTER TABLE ADD COLUMN SQL statement for MySQL."""
        table = self.get_qualified_table_name(table_name, schema)
        column_def = self._generate_column_definition(column)
        
        return f"ALTER TABLE {table} ADD COLUMN {column_def}"
    
    def generate_drop_column_sql(self, table_name: str, column_name: str, schema: Optional[str] = None) -> str:
        """Generate ALTER TABLE DROP COLUMN SQL statement for MySQL."""
        table = self.get_qualified_table_name(table_name, schema)
        column = self.quote_identifier(column_name)
        
        return f"ALTER TABLE {table} DROP COLUMN {column}"
    
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier for MySQL (uses backticks)."""
        return f"`{identifier}`"
    
    def get_current_timestamp_sql(self) -> str:
        """Get the SQL expression for current timestamp in MySQL."""
        return "CURRENT_TIMESTAMP" 