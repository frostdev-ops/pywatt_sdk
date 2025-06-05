"""
MySQL database implementation for PyWatt Python SDK.

This module provides a MySQL-specific implementation of the DatabaseConnection
interface using aiomysql for async database operations.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote_plus

import aiomysql
from aiomysql import Pool, Connection, Cursor

from .database import (
    DatabaseConnection, DatabaseTransaction, DatabaseRow, DatabaseConfig,
    DatabaseType, DatabaseValue, DatabaseError, ConnectionError,
    QueryError, TransactionError, PoolError, ConfigurationError
)

logger = logging.getLogger(__name__)


class MySqlRow(DatabaseRow):
    """MySQL row implementation using aiomysql cursor results."""
    
    def __init__(self, row_data: tuple, description: tuple):
        self.row_data = row_data
        self.columns = {desc[0]: i for i, desc in enumerate(description)}
    
    def _get_value(self, column: str) -> Any:
        """Get raw value for a column."""
        if column not in self.columns:
            raise QueryError(f"Column '{column}' not found")
        index = self.columns[column]
        return self.row_data[index]
    
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
        # MySQL returns 1/0 for boolean values
        if isinstance(value, int):
            return bool(value)
        return bool(value)
    
    def get_bytes(self, column: str) -> bytes:
        """Get a column value as bytes."""
        value = self._get_value(column)
        if value is None:
            raise QueryError(f"Column '{column}' is NULL")
        if isinstance(value, bytes):
            return value
        if isinstance(value, bytearray):
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
            if value is None:
                return None
            if isinstance(value, int):
                return bool(value)
            return bool(value)
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
            if isinstance(value, bytearray):
                return bytes(value)
            return str(value).encode('utf-8')
        except (QueryError, ValueError, TypeError):
            return None


class MySqlTransaction(DatabaseTransaction):
    """MySQL transaction implementation."""
    
    def __init__(self, connection: Connection):
        self.connection = connection
        self._started = False
    
    async def _ensure_started(self):
        """Ensure transaction is started."""
        if not self._started:
            await self.connection.begin()
            self._started = True
    
    async def execute(self, query: str, params: List[DatabaseValue]) -> int:
        """Execute a query within the transaction that returns no rows."""
        await self._ensure_started()
        try:
            param_values = [self._convert_param(p) for p in params]
            async with self.connection.cursor() as cursor:
                await cursor.execute(query, param_values)
                return cursor.rowcount
        except Exception as e:
            raise QueryError(f"Failed to execute query: {e}")
    
    async def query(self, query: str, params: List[DatabaseValue]) -> List[DatabaseRow]:
        """Execute a query within the transaction that returns rows."""
        await self._ensure_started()
        try:
            param_values = [self._convert_param(p) for p in params]
            async with self.connection.cursor() as cursor:
                await cursor.execute(query, param_values)
                rows = await cursor.fetchall()
                return [MySqlRow(row, cursor.description) for row in rows]
        except Exception as e:
            raise QueryError(f"Failed to execute query: {e}")
    
    async def query_one(self, query: str, params: List[DatabaseValue]) -> Optional[DatabaseRow]:
        """Execute a query within the transaction that returns a single row."""
        await self._ensure_started()
        try:
            param_values = [self._convert_param(p) for p in params]
            async with self.connection.cursor() as cursor:
                await cursor.execute(query, param_values)
                row = await cursor.fetchone()
                return MySqlRow(row, cursor.description) if row else None
        except Exception as e:
            raise QueryError(f"Failed to execute query: {e}")
    
    async def commit(self) -> None:
        """Commit the transaction."""
        try:
            if self._started:
                await self.connection.commit()
                self._started = False
        except Exception as e:
            raise TransactionError(f"Failed to commit transaction: {e}")
    
    async def rollback(self) -> None:
        """Rollback the transaction."""
        try:
            if self._started:
                await self.connection.rollback()
                self._started = False
        except Exception as e:
            raise TransactionError(f"Failed to rollback transaction: {e}")
    
    def _convert_param(self, param: DatabaseValue) -> Any:
        """Convert DatabaseValue to aiomysql-compatible parameter."""
        if param.value is None:
            return None
        # MySQL doesn't support array parameters directly
        if hasattr(param, 'value') and isinstance(param.value, list):
            raise QueryError("MySQL doesn't support array parameters directly")
        return param.value


class MySqlConnection(DatabaseConnection):
    """MySQL database connection implementation."""
    
    def __init__(self, pool: Pool):
        self.pool = pool
    
    @classmethod
    async def connect(cls, config: DatabaseConfig) -> 'MySqlConnection':
        """Create a MySQL connection from configuration."""
        try:
            pool = await aiomysql.create_pool(
                host=config.host or "localhost",
                port=config.port or 3306,
                user=config.username,
                password=config.password,
                db=config.database,
                charset=config.extra_params.get("charset", "utf8mb4"),
                minsize=config.pool.min_connections,
                maxsize=config.pool.max_connections,
                pool_recycle=config.pool.max_lifetime_seconds,
                autocommit=False,  # We handle transactions explicitly
            )
            
            return cls(pool)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MySQL: {e}")
    
    async def execute(self, query: str, params: List[DatabaseValue]) -> int:
        """Execute a query that returns no rows."""
        async with self.pool.acquire() as connection:
            try:
                param_values = [self._convert_param(p) for p in params]
                async with connection.cursor() as cursor:
                    await cursor.execute(query, param_values)
                    await connection.commit()
                    return cursor.rowcount
            except Exception as e:
                await connection.rollback()
                raise QueryError(f"Failed to execute query: {e}")
    
    async def query(self, query: str, params: List[DatabaseValue]) -> List[DatabaseRow]:
        """Execute a query that returns rows."""
        async with self.pool.acquire() as connection:
            try:
                param_values = [self._convert_param(p) for p in params]
                async with connection.cursor() as cursor:
                    await cursor.execute(query, param_values)
                    rows = await cursor.fetchall()
                    return [MySqlRow(row, cursor.description) for row in rows]
            except Exception as e:
                raise QueryError(f"Failed to execute query: {e}")
    
    async def query_one(self, query: str, params: List[DatabaseValue]) -> Optional[DatabaseRow]:
        """Execute a query that returns a single row."""
        async with self.pool.acquire() as connection:
            try:
                param_values = [self._convert_param(p) for p in params]
                async with connection.cursor() as cursor:
                    await cursor.execute(query, param_values)
                    row = await cursor.fetchone()
                    return MySqlRow(row, cursor.description) if row else None
            except Exception as e:
                raise QueryError(f"Failed to execute query: {e}")
    
    async def begin_transaction(self) -> DatabaseTransaction:
        """Begin a transaction."""
        try:
            connection = await self.pool.acquire()
            return MySqlTransaction(connection)
        except Exception as e:
            raise TransactionError(f"Failed to begin transaction: {e}")
    
    def get_database_type(self) -> DatabaseType:
        """Get the database type."""
        return DatabaseType.MYSQL
    
    async def ping(self) -> None:
        """Check if the connection is alive."""
        async with self.pool.acquire() as connection:
            try:
                await connection.ping()
            except Exception as e:
                raise ConnectionError(f"Failed to ping database: {e}")
    
    async def close(self) -> None:
        """Close the connection pool."""
        try:
            self.pool.close()
            await self.pool.wait_closed()
        except Exception as e:
            logger.warning(f"Error closing MySQL pool: {e}")
    
    def _convert_param(self, param: DatabaseValue) -> Any:
        """Convert DatabaseValue to aiomysql-compatible parameter."""
        if param.value is None:
            return None
        # MySQL doesn't support array parameters directly
        if hasattr(param, 'value') and isinstance(param.value, list):
            raise QueryError("MySQL doesn't support array parameters directly")
        return param.value 