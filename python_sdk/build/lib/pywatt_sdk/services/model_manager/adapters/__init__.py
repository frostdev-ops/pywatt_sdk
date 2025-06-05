"""Database adapters for the Model Manager."""

from .base import DatabaseAdapter
from .sqlite import SqliteAdapter
from .postgres import PostgresAdapter
from .mysql import MySqlAdapter

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.database import DatabaseType


def get_adapter_for_database_type(db_type: "DatabaseType") -> DatabaseAdapter:
    """Get a database adapter for the specified database type.
    
    Args:
        db_type: The database type to get an adapter for
        
    Returns:
        A DatabaseAdapter implementation for the specified database type
    """
    from data.database import DatabaseType
    
    if db_type == DatabaseType.SQLITE:
        return SqliteAdapter()
    elif db_type == DatabaseType.POSTGRESQL:
        return PostgresAdapter()
    elif db_type == DatabaseType.MYSQL:
        return MySqlAdapter()
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


__all__ = [
    "DatabaseAdapter",
    "SqliteAdapter",
    "PostgresAdapter",
    "MySqlAdapter",
    "get_adapter_for_database_type",
] 