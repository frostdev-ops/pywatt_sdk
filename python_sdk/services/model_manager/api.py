"""Public API functions for the Model Manager."""

from typing import TYPE_CHECKING, List, Optional

from .definitions import ModelDescriptor
from .errors import ModelDefinitionError, UnsupportedFeatureError
from .generator import ModelGenerator
from .builder import ModelBuilder
from .adapters import get_adapter_for_database_type

if TYPE_CHECKING:
    from data.database import DatabaseType


def create_generator_for_database(db_type: "DatabaseType") -> ModelGenerator:
    """Create a new ModelGenerator for the specified database type.
    
    This is a convenience function that combines get_adapter_for_database_type
    and ModelGenerator creation into a single call.
    
    Args:
        db_type: The database type to create a generator for
        
    Returns:
        A ModelGenerator configured for the specified database type
    """
    adapter = get_adapter_for_database_type(db_type)
    return ModelGenerator(adapter)


def validate_model(model: ModelDescriptor) -> None:
    """Validate a model descriptor for common issues.
    
    This function performs basic validation on a model descriptor to catch
    common configuration errors before attempting to generate SQL or apply
    the model to a database.
    
    Args:
        model: The model descriptor to validate
        
    Raises:
        ModelDefinitionError: If the model is invalid
    """
    # Check that table name is not empty
    if not model.name or not model.name.strip():
        raise ModelDefinitionError("Table name cannot be empty")
    
    # Check that there is at least one column
    if not model.columns:
        raise ModelDefinitionError("Model must have at least one column")
    
    # Check for duplicate column names
    column_names = set()
    for column in model.columns:
        if not column.name or not column.name.strip():
            raise ModelDefinitionError("Column name cannot be empty")
        
        if column.name in column_names:
            raise ModelDefinitionError(f"Duplicate column name: {column.name}")
        column_names.add(column.name)
    
    # Check primary key configuration
    pk_columns_from_flags = [
        col.name for col in model.columns if col.is_primary_key
    ]
    
    if model.primary_key:
        if pk_columns_from_flags:
            raise ModelDefinitionError(
                "Cannot specify both table-level primary key and column-level primary key flags"
            )
        
        # Verify all PK columns exist
        for pk_col in model.primary_key:
            if pk_col not in column_names:
                raise ModelDefinitionError(
                    f"Primary key column '{pk_col}' does not exist in table"
                )
    
    # Check auto-increment constraints
    auto_increment_columns = [
        col for col in model.columns if col.auto_increment
    ]
    
    if len(auto_increment_columns) > 1:
        raise ModelDefinitionError(
            "Only one column can have auto_increment enabled"
        )
    
    if auto_increment_columns:
        auto_col = auto_increment_columns[0]
        
        # Check if it's part of primary key
        is_pk = auto_col.is_primary_key or (
            model.primary_key and auto_col.name in model.primary_key
        )
        
        if not is_pk:
            raise ModelDefinitionError(
                "Auto-increment column must be part of the primary key"
            )
        
        # Check that auto-increment column is an integer type
        valid_types = ["Integer", "SmallInt", "BigInt"]
        if auto_col.data_type.type_name not in valid_types:
            raise ModelDefinitionError(
                "Auto-increment column must be an integer type"
            )
    
    # Validate foreign key constraints
    from .definitions import ForeignKeyConstraint
    
    for constraint in model.constraints:
        if isinstance(constraint, ForeignKeyConstraint):
            if len(constraint.columns) != len(constraint.references_columns):
                raise ModelDefinitionError(
                    "Foreign key must have the same number of columns as referenced columns"
                )
            
            # Verify all FK columns exist
            for fk_col in constraint.columns:
                if fk_col not in column_names:
                    raise ModelDefinitionError(
                        f"Foreign key column '{fk_col}' does not exist in table"
                    )
    
    # Validate index definitions
    for index in model.indexes:
        if not index.columns:
            raise ModelDefinitionError(
                "Index must specify at least one column"
            )
        
        # Verify all index columns exist
        for idx_col in index.columns:
            if idx_col not in column_names:
                raise ModelDefinitionError(
                    f"Index column '{idx_col}' does not exist in table"
                )


def generate_complete_sql(
    model: ModelDescriptor,
    db_type: "DatabaseType"
) -> str:
    """Generate a complete SQL script for creating a model and all its associated objects.
    
    This function generates SQL for creating enum types (PostgreSQL), the table itself,
    and all indexes defined in the model. It's a convenience function that combines
    multiple generator calls.
    
    Args:
        model: The model descriptor to generate SQL for
        db_type: The target database type
        
    Returns:
        A complete SQL script as a string
        
    Raises:
        ModelDefinitionError: If the model is invalid
        SqlGenerationError: If SQL generation fails
    """
    # Validate the model first
    validate_model(model)
    
    generator = create_generator_for_database(db_type)
    parts = []
    
    # Generate enum types for PostgreSQL
    from data.database import DatabaseType
    if db_type == DatabaseType.POSTGRESQL:
        enum_stmts = generator.generate_enum_types(model)
        for stmt in enum_stmts:
            parts.append(stmt)
            parts.append(";\n\n")
    
    # Generate the main table creation script
    table_script = generator.generate_create_table_script(model)
    parts.append(table_script)
    
    return "".join(parts)


def create_simple_model(
    table_name: str,
    schema_name: Optional[str] = None
) -> ModelBuilder:
    """Create a simple model with basic columns for common use cases.
    
    This is a convenience function for creating models with standard patterns
    like auto-incrementing ID, timestamps, etc.
    
    Args:
        table_name: The name of the table
        schema_name: Optional schema name
        
    Returns:
        A ModelBuilder for further customization
    """
    return ModelBuilder(table_name, schema_name).add_id_column() 