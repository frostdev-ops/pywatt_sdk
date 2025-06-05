"""Model Manager for applying models to databases."""

import asyncio
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from .definitions import ModelDescriptor
from .generator import ModelGenerator
from .errors import ModelApplicationError, ModelDefinitionError
from .api import validate_model, create_generator_for_database

if TYPE_CHECKING:
    from data.database import DatabaseConnection, DatabaseType


class ModelManagerConfig:
    """Configuration for the Model Manager."""
    
    def __init__(
        self,
        database_connection: "DatabaseConnection",
        database_type: "DatabaseType",
        auto_create_schemas: bool = True,
        dry_run: bool = False,
    ):
        """Initialize the configuration.
        
        Args:
            database_connection: Database connection to use
            database_type: Type of database
            auto_create_schemas: Whether to automatically create schemas
            dry_run: Whether to only generate SQL without executing
        """
        self.database_connection = database_connection
        self.database_type = database_type
        self.auto_create_schemas = auto_create_schemas
        self.dry_run = dry_run


class ModelManager:
    """Manages database models and applies them to the database."""
    
    def __init__(
        self,
        config: ModelManagerConfig,
        models: List[ModelDescriptor],
    ):
        """Initialize the Model Manager.
        
        Args:
            config: Configuration for the manager
            models: List of models to manage
        """
        self.config = config
        self.models = models
        self.generator = create_generator_for_database(config.database_type)
        self._applied_models: List[str] = []
    
    async def apply_models(self) -> List[str]:
        """Apply all models to the database.
        
        Returns:
            List of SQL statements that were executed
            
        Raises:
            ModelApplicationError: If applying models fails
        """
        try:
            all_statements = []
            
            # Validate all models first
            for model in self.models:
                validate_model(model)
            
            # Create schemas if needed
            if self.config.auto_create_schemas:
                schema_statements = await self._create_schemas()
                all_statements.extend(schema_statements)
            
            # Apply each model
            for model in self.models:
                statements = await self._apply_model(model)
                all_statements.extend(statements)
                self._applied_models.append(model.name)
            
            return all_statements
            
        except Exception as e:
            raise ModelApplicationError(f"Failed to apply models: {e}", e)
    
    async def _create_schemas(self) -> List[str]:
        """Create schemas for models that need them.
        
        Returns:
            List of SQL statements executed
        """
        schemas = set()
        for model in self.models:
            if model.schema:
                schemas.add(model.schema)
        
        statements = []
        for schema in schemas:
            # Generate CREATE SCHEMA statement
            if self.generator.adapter.supports_schemas():
                stmt = f"CREATE SCHEMA IF NOT EXISTS {self.generator.adapter.quote_identifier(schema)}"
                statements.append(stmt)
                
                if not self.config.dry_run:
                    await self.config.database_connection.execute(stmt)
        
        return statements
    
    async def _apply_model(self, model: ModelDescriptor) -> List[str]:
        """Apply a single model to the database.
        
        Args:
            model: Model to apply
            
        Returns:
            List of SQL statements executed
        """
        statements = []
        
        # Generate enum types for PostgreSQL
        if self.generator.adapter.supports_enum_types():
            enum_stmts = self.generator.generate_enum_types(model)
            for stmt in enum_stmts:
                statements.append(stmt)
                if not self.config.dry_run:
                    await self.config.database_connection.execute(stmt)
        
        # Generate and execute CREATE TABLE
        create_table_sql = self.generator.adapter.generate_create_table_sql(model)
        statements.append(create_table_sql)
        if not self.config.dry_run:
            await self.config.database_connection.execute(create_table_sql)
        
        # Generate and execute CREATE INDEX statements
        for index in model.indexes:
            index_sql = self.generator.adapter.generate_create_index_sql(
                model.name,
                index,
                model.schema
            )
            statements.append(index_sql)
            if not self.config.dry_run:
                await self.config.database_connection.execute(index_sql)
        
        return statements
    
    async def drop_models(self, if_exists: bool = True) -> List[str]:
        """Drop all managed models from the database.
        
        Args:
            if_exists: Whether to use IF EXISTS clause
            
        Returns:
            List of SQL statements executed
        """
        try:
            statements = []
            
            # Drop in reverse order to handle dependencies
            for model in reversed(self.models):
                drop_sql = self.generator.adapter.generate_drop_table_sql(
                    model.name,
                    model.schema,
                    if_exists
                )
                statements.append(drop_sql)
                
                if not self.config.dry_run:
                    await self.config.database_connection.execute(drop_sql)
            
            return statements
            
        except Exception as e:
            raise ModelApplicationError(f"Failed to drop models: {e}", e)
    
    async def add_column(
        self,
        table_name: str,
        column: "ColumnDescriptor",
        schema: Optional[str] = None
    ) -> str:
        """Add a column to an existing table.
        
        Args:
            table_name: Name of the table
            column: Column to add
            schema: Optional schema name
            
        Returns:
            SQL statement executed
        """
        try:
            sql = self.generator.adapter.generate_add_column_sql(
                table_name,
                column,
                schema
            )
            
            if not self.config.dry_run:
                await self.config.database_connection.execute(sql)
            
            return sql
            
        except Exception as e:
            raise ModelApplicationError(f"Failed to add column: {e}", e)
    
    async def drop_column(
        self,
        table_name: str,
        column_name: str,
        schema: Optional[str] = None
    ) -> str:
        """Drop a column from an existing table.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column to drop
            schema: Optional schema name
            
        Returns:
            SQL statement executed
        """
        try:
            sql = self.generator.adapter.generate_drop_column_sql(
                table_name,
                column_name,
                schema
            )
            
            if not self.config.dry_run:
                await self.config.database_connection.execute(sql)
            
            return sql
            
        except Exception as e:
            raise ModelApplicationError(f"Failed to drop column: {e}", e)
    
    def get_applied_models(self) -> List[str]:
        """Get list of models that have been applied.
        
        Returns:
            List of model names
        """
        return self._applied_models.copy()
    
    def generate_migration_script(self) -> str:
        """Generate a complete migration script for all models.
        
        Returns:
            SQL script with all CREATE statements
        """
        parts = []
        
        # Add header comment
        parts.append("-- Generated by PyWatt Model Manager")
        parts.append("-- Database Type: " + str(self.config.database_type))
        parts.append("")
        
        # Create schemas
        if self.config.auto_create_schemas:
            schemas = set()
            for model in self.models:
                if model.schema:
                    schemas.add(model.schema)
            
            for schema in schemas:
                if self.generator.adapter.supports_schemas():
                    parts.append(f"CREATE SCHEMA IF NOT EXISTS {self.generator.adapter.quote_identifier(schema)};")
            
            if schemas:
                parts.append("")
        
        # Generate SQL for each model
        for model in self.models:
            parts.append(f"-- Table: {model.name}")
            
            # Enum types
            if self.generator.adapter.supports_enum_types():
                enum_stmts = self.generator.generate_enum_types(model)
                for stmt in enum_stmts:
                    parts.append(stmt + ";")
                if enum_stmts:
                    parts.append("")
            
            # Table
            table_sql = self.generator.adapter.generate_create_table_sql(model)
            parts.append(table_sql + ";")
            parts.append("")
            
            # Indexes
            for index in model.indexes:
                index_sql = self.generator.adapter.generate_create_index_sql(
                    model.name,
                    index,
                    model.schema
                )
                parts.append(index_sql + ";")
            
            if model.indexes:
                parts.append("")
        
        return "\n".join(parts) 