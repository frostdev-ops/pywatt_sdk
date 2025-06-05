"""Base database adapter interface."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from ..definitions import (
    ModelDescriptor,
    ColumnDescriptor,
    DataType,
    Constraint,
    IndexDescriptor,
    ReferentialAction,
)
from ..errors import DatabaseAdapterError


class DatabaseAdapter(ABC):
    """Abstract base class for database-specific adapters.
    
    Each database adapter implements SQL generation for a specific database engine.
    """
    
    @abstractmethod
    def get_type_sql(self, data_type: DataType) -> str:
        """Convert a DataType to database-specific SQL type string.
        
        Args:
            data_type: The data type to convert
            
        Returns:
            SQL type string for the database
        """
        pass
    
    @abstractmethod
    def generate_create_table_sql(self, model: ModelDescriptor) -> str:
        """Generate CREATE TABLE SQL statement.
        
        Args:
            model: The model descriptor
            
        Returns:
            CREATE TABLE SQL statement
        """
        pass
    
    @abstractmethod
    def generate_drop_table_sql(self, table_name: str, schema: Optional[str] = None, if_exists: bool = True) -> str:
        """Generate DROP TABLE SQL statement.
        
        Args:
            table_name: Name of the table to drop
            schema: Optional schema name
            if_exists: Whether to add IF EXISTS clause
            
        Returns:
            DROP TABLE SQL statement
        """
        pass
    
    @abstractmethod
    def generate_create_index_sql(self, table_name: str, index: IndexDescriptor, schema: Optional[str] = None) -> str:
        """Generate CREATE INDEX SQL statement.
        
        Args:
            table_name: Name of the table
            index: Index descriptor
            schema: Optional schema name
            
        Returns:
            CREATE INDEX SQL statement
        """
        pass
    
    @abstractmethod
    def generate_add_column_sql(self, table_name: str, column: ColumnDescriptor, schema: Optional[str] = None) -> str:
        """Generate ALTER TABLE ADD COLUMN SQL statement.
        
        Args:
            table_name: Name of the table
            column: Column descriptor
            schema: Optional schema name
            
        Returns:
            ALTER TABLE ADD COLUMN SQL statement
        """
        pass
    
    @abstractmethod
    def generate_drop_column_sql(self, table_name: str, column_name: str, schema: Optional[str] = None) -> str:
        """Generate ALTER TABLE DROP COLUMN SQL statement.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column to drop
            schema: Optional schema name
            
        Returns:
            ALTER TABLE DROP COLUMN SQL statement
        """
        pass
    
    def generate_enum_types_sql(self, model: ModelDescriptor) -> List[str]:
        """Generate SQL statements for creating enum types (PostgreSQL specific).
        
        Args:
            model: The model descriptor
            
        Returns:
            List of SQL statements for creating enum types
        """
        # Default implementation returns empty list (most databases don't have enum types)
        return []
    
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier (table name, column name, etc.).
        
        Args:
            identifier: The identifier to quote
            
        Returns:
            Quoted identifier
        """
        # Default implementation uses double quotes (SQL standard)
        return f'"{identifier}"'
    
    def get_qualified_table_name(self, table_name: str, schema: Optional[str] = None) -> str:
        """Get fully qualified table name with optional schema.
        
        Args:
            table_name: Table name
            schema: Optional schema name
            
        Returns:
            Qualified table name
        """
        if schema:
            return f"{self.quote_identifier(schema)}.{self.quote_identifier(table_name)}"
        return self.quote_identifier(table_name)
    
    def get_referential_action_sql(self, action: Optional[ReferentialAction]) -> str:
        """Convert ReferentialAction to SQL string.
        
        Args:
            action: The referential action
            
        Returns:
            SQL string for the action
        """
        if action is None:
            return ""
        
        action_map = {
            ReferentialAction.NO_ACTION: "NO ACTION",
            ReferentialAction.RESTRICT: "RESTRICT",
            ReferentialAction.CASCADE: "CASCADE",
            ReferentialAction.SET_NULL: "SET NULL",
            ReferentialAction.SET_DEFAULT: "SET DEFAULT",
        }
        
        return action_map.get(action, "NO ACTION")
    
    def supports_if_not_exists(self) -> bool:
        """Check if the database supports IF NOT EXISTS clause.
        
        Returns:
            True if supported, False otherwise
        """
        return True
    
    def supports_schemas(self) -> bool:
        """Check if the database supports schemas.
        
        Returns:
            True if supported, False otherwise
        """
        return True
    
    def supports_enum_types(self) -> bool:
        """Check if the database supports enum types.
        
        Returns:
            True if supported, False otherwise
        """
        return False
    
    def get_auto_increment_sql(self) -> str:
        """Get the SQL keyword for auto-increment columns.
        
        Returns:
            Auto-increment SQL keyword
        """
        return "AUTO_INCREMENT"
    
    def get_current_timestamp_sql(self) -> str:
        """Get the SQL expression for current timestamp.
        
        Returns:
            Current timestamp SQL expression
        """
        return "CURRENT_TIMESTAMP" 