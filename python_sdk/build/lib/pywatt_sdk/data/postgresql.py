"""
PostgreSQL database implementation for PyWatt Python SDK.

This module provides a PostgreSQL-specific implementation of the DatabaseConnection
interface using asyncpg for high-performance async database operations.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote_plus

import asyncpg
from asyncpg import Connection, Pool, Record

from .database import (
    DatabaseConnection, DatabaseTransaction, DatabaseRow, DatabaseConfig,
    DatabaseType, DatabaseValue, DatabaseError, ConnectionError,
    QueryError, TransactionError, PoolError, ConfigurationError
)

logger = logging.getLogger(__name__)


class PostgresRow(DatabaseRow):
    """PostgreSQL row implementation using asyncpg Record."""
    
    def __init__(self, record: Record):
        self.record = record
    
    def _get_value(self, column: str) -> Any:
        """Get raw value for a column."""
        try:
            return self.record[column]
        except KeyError:
            raise QueryError(f"Column '{column}' not found")
    
    def get_string(self, column: str) -> str:
        """Get a column value as string."""
        value = self._get_value(column)
        if value is None:
            raise QueryError(f"Column '{column}' is NULL")
        return str(value)
    
    def get_int(self, column: str) -> int:
        """Get a column value as integer."""
        value = self._get_value(column)
        if value is None:
            raise QueryError(f"Column '{column}' is NULL")
        return int(value)
    
    def get_float(self, column: str) -> float:
        """Get a column value as float."""
        value = self._get_value(column)
        if value is None:
            raise QueryError(f"Column '{column}' is NULL")
        return float(value)
    
    def get_bool(self, column: str) -> bool:
        """Get a column value as boolean."""
        value = self._get_value(column)
        if value is None:
            raise QueryError(f"Column '{column}' is NULL")
        return bool(value)
    
    def get_bytes(self, column: str) -> bytes:
        """Get a column value as bytes."""
        value = self._get_value(column)
        if value is None:
            raise QueryError(f"Column '{column}' is NULL")
        if isinstance(value, bytes):
            return value
        if isinstance(value, memoryview):
            return bytes(value)
        return str(value).encode('utf-8')
    
    def try_get_string(self, column: str) -> Optional[str]:
        """Try to get a column value as string."""
        try:
            value = self._get_value(column)
            return str(value) if value is not None else None
        except QueryError:
            return None
    
    def try_get_int(self, column: str) -> Optional[int]:
        """Try to get a column value as integer."""
        try:
            value = self._get_value(column)
            return int(value) if value is not None else None
        except (QueryError, ValueError, TypeError):
            return None
    
    def try_get_float(self, column: str) -> Optional[float]:
        """Try to get a column value as float."""
        try:
            value = self._get_value(column)
            return float(value) if value is not None else None
        except (QueryError, ValueError, TypeError):
            return None
    
    def try_get_bool(self, column: str) -> Optional[bool]:
        """Try to get a column value as boolean."""
        try:
            value = self._get_value(column)
            return bool(value) if value is not None else None
        except (QueryError, ValueError, TypeError):
            return None
    
    def try_get_bytes(self, column: str) -> Optional[bytes]:
        """Try to get a column value as bytes."""
        try:
            value = self._get_value(column)
            if value is None:
                return None
            if isinstance(value, bytes):
                return value
            if isinstance(value, memoryview):
                return bytes(value)
            return str(value).encode('utf-8')
        except (QueryError, ValueError, TypeError):
            return None


class PostgresTransaction(DatabaseTransaction):
    """PostgreSQL transaction implementation."""
    
    def __init__(self, transaction: asyncpg.Transaction):
        self.transaction = transaction
        self._connection = transaction.connection
    
    async def execute(self, query: str, params: List[DatabaseValue]) -> int:
        """Execute a query within the transaction that returns no rows."""
        try:
            param_values = [self._convert_param(p) for p in params]
            result = await self._connection.execute(query, *param_values)
            # Parse result like "INSERT 0 5" or "UPDATE 3"
            if result.startswith(('INSERT', 'UPDATE', 'DELETE')):
                parts = result.split()
                if len(parts) >= 2:
                    return int(parts[-1])
            return 0
        except Exception as e:
            raise QueryError(f"Failed to execute query: {e}")
    
    async def query(self, query: str, params: List[DatabaseValue]) -> List[DatabaseRow]:
        """Execute a query within the transaction that returns rows."""
        try:
            param_values = [self._convert_param(p) for p in params]
            records = await self._connection.fetch(query, *param_values)
            return [PostgresRow(record) for record in records]
        except Exception as e:
            raise QueryError(f"Failed to execute query: {e}")
    
    async def query_one(self, query: str, params: List[DatabaseValue]) -> Optional[DatabaseRow]:
        """Execute a query within the transaction that returns a single row."""
        try:
            param_values = [self._convert_param(p) for p in params]
            record = await self._connection.fetchrow(query, *param_values)
            return PostgresRow(record) if record else None
        except Exception as e:
            raise QueryError(f"Failed to execute query: {e}")
    
    async def commit(self) -> None:
        """Commit the transaction."""
        try:
            await self.transaction.commit()
        except Exception as e:
            raise TransactionError(f"Failed to commit transaction: {e}")
    
    async def rollback(self) -> None:
        """Rollback the transaction."""
        try:
            await self.transaction.rollback()
        except Exception as e:
            raise TransactionError(f"Failed to rollback transaction: {e}")
    
    def _convert_param(self, param: DatabaseValue) -> Any:
        """Convert DatabaseValue to asyncpg-compatible parameter."""
        return param.value


class PostgresConnection(DatabaseConnection):
    """PostgreSQL database connection implementation."""
    
    def __init__(self, pool: Pool):
        self.pool = pool
    
    @classmethod
    async def connect(cls, config: DatabaseConfig) -> 'PostgresConnection':
        """Create a PostgreSQL connection from configuration."""
        try:
            connection_string = cls._build_connection_string(config)
            
            pool = await asyncpg.create_pool(
                connection_string,
                min_size=config.pool.min_connections,
                max_size=config.pool.max_connections,
                max_inactive_connection_lifetime=config.pool.idle_timeout_seconds,
                command_timeout=config.pool.acquire_timeout_seconds,
            )
            
            return cls(pool)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to PostgreSQL: {e}")
    
    @staticmethod
    def _build_connection_string(config: DatabaseConfig) -> str:
        """Build PostgreSQL connection string from config."""
        host = config.host or "localhost"
        port = config.port or 5432
        database = config.database
        
        # Build base connection string
        if config.username and config.password:
            # URL-encode username and password to handle special characters
            username = quote_plus(config.username)
            password = quote_plus(config.password)
            connection_string = f"postgresql://{username}:{password}@{host}:{port}/{database}"
        elif config.username:
            username = quote_plus(config.username)
            connection_string = f"postgresql://{username}@{host}:{port}/{database}"
        else:
            connection_string = f"postgresql://{host}:{port}/{database}"
        
        # Add SSL mode if specified
        params = []
        if config.ssl_mode:
            params.append(f"sslmode={config.ssl_mode}")
        
        # Add extra parameters
        for key, value in (config.extra_params or {}).items():
            params.append(f"{key}={value}")
        
        if params:
            connection_string += "?" + "&".join(params)
        
        return connection_string
    
    async def execute(self, query: str, params: List[DatabaseValue]) -> int:
        """Execute a query that returns no rows."""
        async with self.pool.acquire() as connection:
            try:
                param_values = [self._convert_param(p) for p in params]
                result = await connection.execute(query, *param_values)
                # Parse result like "INSERT 0 5" or "UPDATE 3"
                if result.startswith(('INSERT', 'UPDATE', 'DELETE')):
                    parts = result.split()
                    if len(parts) >= 2:
                        return int(parts[-1])
                return 0
            except Exception as e:
                raise QueryError(f"Failed to execute query: {e}")
    
    async def query(self, query: str, params: List[DatabaseValue]) -> List[DatabaseRow]:
        """Execute a query that returns rows."""
        async with self.pool.acquire() as connection:
            try:
                param_values = [self._convert_param(p) for p in params]
                records = await connection.fetch(query, *param_values)
                return [PostgresRow(record) for record in records]
            except Exception as e:
                raise QueryError(f"Failed to execute query: {e}")
    
    async def query_one(self, query: str, params: List[DatabaseValue]) -> Optional[DatabaseRow]:
        """Execute a query that returns a single row."""
        async with self.pool.acquire() as connection:
            try:
                param_values = [self._convert_param(p) for p in params]
                record = await connection.fetchrow(query, *param_values)
                return PostgresRow(record) if record else None
            except Exception as e:
                raise QueryError(f"Failed to execute query: {e}")
    
    async def begin_transaction(self) -> DatabaseTransaction:
        """Begin a transaction."""
        try:
            connection = await self.pool.acquire()
            transaction = connection.transaction()
            await transaction.start()
            return PostgresTransaction(transaction)
        except Exception as e:
            raise TransactionError(f"Failed to begin transaction: {e}")
    
    def get_database_type(self) -> DatabaseType:
        """Get the database type."""
        return DatabaseType.POSTGRES
    
    async def ping(self) -> None:
        """Check if the connection is alive."""
        async with self.pool.acquire() as connection:
            try:
                await connection.fetchval("SELECT 1")
            except Exception as e:
                raise ConnectionError(f"Failed to ping database: {e}")
    
    async def close(self) -> None:
        """Close the connection pool."""
        try:
            await self.pool.close()
        except Exception as e:
            logger.warning(f"Error closing PostgreSQL pool: {e}")
    
    def _convert_param(self, param: DatabaseValue) -> Any:
        """Convert DatabaseValue to asyncpg-compatible parameter."""
        return param.value 