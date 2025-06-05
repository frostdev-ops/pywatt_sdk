"""SQL generator for database models."""

from typing import List, Optional

from .definitions import ModelDescriptor, IndexDescriptor
from .adapters import DatabaseAdapter
from .errors import SqlGenerationError


class ModelGenerator:
    """Generates SQL statements for database models using a specific adapter."""
    
    def __init__(self, adapter: DatabaseAdapter):
        """Initialize the generator with a database adapter.
        
        Args:
            adapter: Database adapter for SQL generation
        """
        self.adapter = adapter
    
    def generate_create_table_script(self, model: ModelDescriptor) -> str:
        """Generate a complete CREATE TABLE script including indexes.
        
        Args:
            model: Model descriptor
            
        Returns:
            Complete SQL script with CREATE TABLE and CREATE INDEX statements
        """
        try:
            parts = []
            
            # Generate CREATE TABLE statement
            create_table_sql = self.adapter.generate_create_table_sql(model)
            parts.append(create_table_sql)
            parts.append(";")
            
            # Generate CREATE INDEX statements
            for index in model.indexes:
                index_sql = self.adapter.generate_create_index_sql(
                    model.name,
                    index,
                    model.schema
                )
                parts.append("\n")
                parts.append(index_sql)
                parts.append(";")
            
            return "".join(parts)
            
        except Exception as e:
            raise SqlGenerationError(f"Failed to generate CREATE TABLE script: {e}", e)
    
    def generate_drop_table_script(
        self,
        table_name: str,
        schema: Optional[str] = None,
        if_exists: bool = True
    ) -> str:
        """Generate DROP TABLE script.
        
        Args:
            table_name: Name of the table to drop
            schema: Optional schema name
            if_exists: Whether to add IF EXISTS clause
            
        Returns:
            DROP TABLE SQL statement
        """
        try:
            return self.adapter.generate_drop_table_sql(table_name, schema, if_exists)
        except Exception as e:
            raise SqlGenerationError(f"Failed to generate DROP TABLE script: {e}", e)
    
    def generate_alter_table_add_column(
        self,
        table_name: str,
        column: "ColumnDescriptor",
        schema: Optional[str] = None
    ) -> str:
        """Generate ALTER TABLE ADD COLUMN statement.
        
        Args:
            table_name: Name of the table
            column: Column descriptor
            schema: Optional schema name
            
        Returns:
            ALTER TABLE ADD COLUMN SQL statement
        """
        try:
            return self.adapter.generate_add_column_sql(table_name, column, schema)
        except Exception as e:
            raise SqlGenerationError(f"Failed to generate ADD COLUMN script: {e}", e)
    
    def generate_alter_table_drop_column(
        self,
        table_name: str,
        column_name: str,
        schema: Optional[str] = None
    ) -> str:
        """Generate ALTER TABLE DROP COLUMN statement.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column to drop
            schema: Optional schema name
            
        Returns:
            ALTER TABLE DROP COLUMN SQL statement
        """
        try:
            return self.adapter.generate_drop_column_sql(table_name, column_name, schema)
        except Exception as e:
            raise SqlGenerationError(f"Failed to generate DROP COLUMN script: {e}", e)
    
    def generate_create_index(
        self,
        table_name: str,
        index: IndexDescriptor,
        schema: Optional[str] = None
    ) -> str:
        """Generate CREATE INDEX statement.
        
        Args:
            table_name: Name of the table
            index: Index descriptor
            schema: Optional schema name
            
        Returns:
            CREATE INDEX SQL statement
        """
        try:
            return self.adapter.generate_create_index_sql(table_name, index, schema)
        except Exception as e:
            raise SqlGenerationError(f"Failed to generate CREATE INDEX script: {e}", e)
    
    def generate_enum_types(self, model: ModelDescriptor) -> List[str]:
        """Generate enum type creation statements (PostgreSQL specific).
        
        Args:
            model: Model descriptor
            
        Returns:
            List of CREATE TYPE statements for enums
        """
        try:
            return self.adapter.generate_enum_types_sql(model)
        except Exception as e:
            raise SqlGenerationError(f"Failed to generate enum types: {e}", e)
    
    def adapter(self) -> DatabaseAdapter:
        """Get the underlying database adapter.
        
        Returns:
            The database adapter
        """
        return self.adapter 