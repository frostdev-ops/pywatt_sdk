"""
Database abstraction layer for PyWatt Python SDK.

This module provides a unified interface for database operations across different
database types (SQLite, PostgreSQL, MySQL) with support for proxy connections
through the orchestrator.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..core.error import PyWattSDKError


class DatabaseType(Enum):
    """Supported database types."""
    POSTGRES = "postgres"
    MYSQL = "mysql"
    SQLITE = "sqlite"


@dataclass
class PoolConfig:
    """Configuration for connection pool."""
    max_connections: int = 10
    min_connections: int = 2
    idle_timeout_seconds: int = 300  # 5 minutes
    max_lifetime_seconds: int = 1800  # 30 minutes
    acquire_timeout_seconds: int = 30


@dataclass
class DatabaseConfig:
    """Database configuration for establishing connections."""
    db_type: DatabaseType
    database: str  # Database name for Postgres/MySQL or file path for SQLite
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    ssl_mode: Optional[str] = None
    pool: PoolConfig = None
    extra_params: Optional[Dict[str, str]] = None
    
    def __post_init__(self):
        if self.pool is None:
            self.pool = PoolConfig()
        if self.extra_params is None:
            self.extra_params = {}
    
    @classmethod
    def postgres(cls, host: str, port: int, database: str, username: str, password: str) -> 'DatabaseConfig':
        """Create PostgreSQL configuration."""
        return cls(
            db_type=DatabaseType.POSTGRES,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password
        )
    
    @classmethod
    def mysql(cls, host: str, port: int, database: str, username: str, password: str) -> 'DatabaseConfig':
        """Create MySQL configuration."""
        return cls(
            db_type=DatabaseType.MYSQL,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password
        )
    
    @classmethod
    def sqlite(cls, database_path: str) -> 'DatabaseConfig':
        """Create SQLite configuration."""
        return cls(
            db_type=DatabaseType.SQLITE,
            database=database_path
        )


class DatabaseError(PyWattSDKError):
    """Base class for database-related errors."""
    pass


class ConnectionError(DatabaseError):
    """Database connection error."""
    pass


class QueryError(DatabaseError):
    """Database query error."""
    pass


class TransactionError(DatabaseError):
    """Database transaction error."""
    pass


class PoolError(DatabaseError):
    """Connection pool error."""
    pass


class ConfigurationError(DatabaseError):
    """Database configuration error."""
    pass


class MigrationError(DatabaseError):
    """Database migration error."""
    pass


class SerializationError(DatabaseError):
    """Database serialization/deserialization error."""
    pass


class DatabaseValue:
    """Represents a parameter value for database queries."""
    
    def __init__(self, value: Any):
        self.value = value
    
    @classmethod
    def null(cls) -> 'DatabaseValue':
        """Create a null value."""
        return cls(None)
    
    @classmethod
    def boolean(cls, value: bool) -> 'DatabaseValue':
        """Create a boolean value."""
        return cls(value)
    
    @classmethod
    def integer(cls, value: int) -> 'DatabaseValue':
        """Create an integer value."""
        return cls(value)
    
    @classmethod
    def float(cls, value: float) -> 'DatabaseValue':
        """Create a float value."""
        return cls(value)
    
    @classmethod
    def text(cls, value: str) -> 'DatabaseValue':
        """Create a text value."""
        return cls(value)
    
    @classmethod
    def blob(cls, value: bytes) -> 'DatabaseValue':
        """Create a blob value."""
        return cls(value)
    
    @classmethod
    def array(cls, values: List['DatabaseValue']) -> 'DatabaseValue':
        """Create an array value."""
        return cls([v.value for v in values])


class DatabaseRow(ABC):
    """Represents a row from a database query."""
    
    @abstractmethod
    def get_string(self, column: str) -> str:
        """Get a column value as string."""
        pass
    
    @abstractmethod
    def get_int(self, column: str) -> int:
        """Get a column value as integer."""
        pass
    
    @abstractmethod
    def get_float(self, column: str) -> float:
        """Get a column value as float."""
        pass
    
    @abstractmethod
    def get_bool(self, column: str) -> bool:
        """Get a column value as boolean."""
        pass
    
    @abstractmethod
    def get_bytes(self, column: str) -> bytes:
        """Get a column value as bytes."""
        pass
    
    @abstractmethod
    def try_get_string(self, column: str) -> Optional[str]:
        """Try to get a column value as string, returning None if missing or NULL."""
        pass
    
    @abstractmethod
    def try_get_int(self, column: str) -> Optional[int]:
        """Try to get a column value as integer, returning None if missing or NULL."""
        pass
    
    @abstractmethod
    def try_get_float(self, column: str) -> Optional[float]:
        """Try to get a column value as float, returning None if missing or NULL."""
        pass
    
    @abstractmethod
    def try_get_bool(self, column: str) -> Optional[bool]:
        """Try to get a column value as boolean, returning None if missing or NULL."""
        pass
    
    @abstractmethod
    def try_get_bytes(self, column: str) -> Optional[bytes]:
        """Try to get a column value as bytes, returning None if missing or NULL."""
        pass


class DatabaseTransaction(ABC):
    """Database transaction interface."""
    
    @abstractmethod
    async def execute(self, query: str, params: List[DatabaseValue]) -> int:
        """Execute a query within the transaction that returns no rows."""
        pass
    
    @abstractmethod
    async def query(self, query: str, params: List[DatabaseValue]) -> List[DatabaseRow]:
        """Execute a query within the transaction that returns rows."""
        pass
    
    @abstractmethod
    async def query_one(self, query: str, params: List[DatabaseValue]) -> Optional[DatabaseRow]:
        """Execute a query within the transaction that returns a single row."""
        pass
    
    @abstractmethod
    async def commit(self) -> None:
        """Commit the transaction."""
        pass
    
    @abstractmethod
    async def rollback(self) -> None:
        """Rollback the transaction."""
        pass


class DatabaseConnection(ABC):
    """Core database connection interface."""
    
    @abstractmethod
    async def execute(self, query: str, params: List[DatabaseValue]) -> int:
        """Execute a query that returns no rows."""
        pass
    
    @abstractmethod
    async def query(self, query: str, params: List[DatabaseValue]) -> List[DatabaseRow]:
        """Execute a query that returns rows."""
        pass
    
    @abstractmethod
    async def query_one(self, query: str, params: List[DatabaseValue]) -> Optional[DatabaseRow]:
        """Execute a query that returns a single row."""
        pass
    
    @abstractmethod
    async def begin_transaction(self) -> DatabaseTransaction:
        """Begin a transaction."""
        pass
    
    @abstractmethod
    def get_database_type(self) -> DatabaseType:
        """Get the underlying database type."""
        pass
    
    @abstractmethod
    async def ping(self) -> None:
        """Check if the connection is alive."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        pass


# Proxy connection for orchestrator services
class ProxyDatabaseConnection(DatabaseConnection):
    """Database connection that proxies operations through the orchestrator."""
    
    def __init__(self, config: DatabaseConfig, connection_id: str):
        self.config = config
        self.connection_id = connection_id
        self._active_transactions = []
    
    @classmethod
    async def connect(cls, config: DatabaseConfig) -> 'ProxyDatabaseConnection':
        """Create a proxy database connection."""
        from ..communication.ipc_types import ServiceRequest, ServiceType
        from ..communication.ipc import send_ipc_message
        import uuid
        
        # Create a unique ID for this connection request
        request_id = f"db_request_{uuid.uuid4()}"
        
        # Create a service request
        request = ServiceRequest(
            id=request_id,
            service_type=ServiceType.DATABASE,
            config=config.__dict__
        )
        
        # Send the request to the orchestrator
        try:
            response = await send_ipc_message(request)
            
            # Parse the response
            if not response.get("success", False):
                raise ConnectionError(f"Failed to connect to database: {response.get('error', 'Unknown error')}")
            
            connection_id = response.get("connection_id")
            if not connection_id:
                raise ConnectionError("No connection ID returned from orchestrator")
            
            return cls(config, connection_id)
            
        except Exception as e:
            raise ConnectionError(f"Failed to establish proxy database connection: {e}")
    
    async def execute(self, query: str, params: List[DatabaseValue]) -> int:
        """Execute a query via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        # Serialize parameters
        serialized_params = [self._serialize_param(p) for p in params]
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="execute",
            params={
                "query": query,
                "params": serialized_params
            }
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise QueryError(f"Query execution failed: {result.get('error', 'Unknown error')}")
            
            return result.get("result", 0)
            
        except Exception as e:
            raise QueryError(f"Failed to execute query via proxy: {e}")
    
    async def query(self, query: str, params: List[DatabaseValue]) -> List[DatabaseRow]:
        """Execute a query via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        # Serialize parameters
        serialized_params = [self._serialize_param(p) for p in params]
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="query",
            params={
                "query": query,
                "params": serialized_params
            }
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise QueryError(f"Query failed: {result.get('error', 'Unknown error')}")
            
            rows_data = result.get("result", [])
            return [ProxyDatabaseRow(row) for row in rows_data]
            
        except Exception as e:
            raise QueryError(f"Failed to execute query via proxy: {e}")
    
    async def query_one(self, query: str, params: List[DatabaseValue]) -> Optional[DatabaseRow]:
        """Execute a query via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        # Serialize parameters
        serialized_params = [self._serialize_param(p) for p in params]
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="query_one",
            params={
                "query": query,
                "params": serialized_params
            }
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise QueryError(f"Query failed: {result.get('error', 'Unknown error')}")
            
            row_data = result.get("result")
            return ProxyDatabaseRow(row_data) if row_data else None
            
        except Exception as e:
            raise QueryError(f"Failed to execute query via proxy: {e}")
    
    async def begin_transaction(self) -> DatabaseTransaction:
        """Begin a transaction via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        import uuid
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="begin_transaction",
            params={}
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise TransactionError(f"Failed to begin transaction: {result.get('error', 'Unknown error')}")
            
            transaction_id = result.get("result")
            if not transaction_id:
                raise TransactionError("No transaction ID returned")
            
            self._active_transactions.append(transaction_id)
            return ProxyDatabaseTransaction(self.connection_id, transaction_id)
            
        except Exception as e:
            raise TransactionError(f"Failed to begin transaction via proxy: {e}")
    
    def get_database_type(self) -> DatabaseType:
        """Get the database type."""
        return self.config.db_type
    
    async def ping(self) -> None:
        """Ping via orchestrator proxy."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="ping",
            params={}
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise ConnectionError(f"Ping failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            raise ConnectionError(f"Failed to ping database via proxy: {e}")
    
    async def close(self) -> None:
        """Close the proxy connection."""
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        # Rollback any active transactions first
        for transaction_id in self._active_transactions:
            try:
                rollback_op = ServiceOperation(
                    connection_id=self.connection_id,
                    service_type=ServiceType.DATABASE,
                    operation="transaction_rollback",
                    params={"transaction_id": transaction_id}
                )
                await send_ipc_message(rollback_op)
            except:
                pass  # Ignore rollback errors during close
        
        self._active_transactions.clear()
        
        # Close the connection
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="close",
            params={}
        )
        
        try:
            await send_ipc_message(operation)
        except:
            pass  # Ignore close errors
    
    def _serialize_param(self, param: DatabaseValue) -> Any:
        """Serialize a DatabaseValue for IPC transmission."""
        if param.value is None:
            return None
        elif isinstance(param.value, (str, int, float, bool)):
            return param.value
        elif isinstance(param.value, bytes):
            import base64
            return base64.b64encode(param.value).decode('utf-8')
        elif isinstance(param.value, list):
            return [self._serialize_param(DatabaseValue(v)) for v in param.value]
        else:
            return str(param.value)


# Direct database connections (feature-gated)
class SqliteConnection(DatabaseConnection):
    """SQLite database connection."""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._connection = None
    
    @classmethod
    async def connect(cls, config: DatabaseConfig) -> 'SqliteConnection':
        """Create a SQLite connection."""
        try:
            import aiosqlite
        except ImportError:
            raise ConfigurationError("aiosqlite is required for SQLite support. Install with: pip install aiosqlite")
        
        connection = cls(config)
        connection._connection = await aiosqlite.connect(config.database)
        return connection
    
    async def execute(self, query: str, params: List[DatabaseValue]) -> int:
        """Execute a query that returns no rows."""
        if not self._connection:
            raise ConnectionError("Not connected to database")
        
        param_values = [p.value for p in params]
        cursor = await self._connection.execute(query, param_values)
        await self._connection.commit()
        return cursor.rowcount
    
    async def query(self, query: str, params: List[DatabaseValue]) -> List[DatabaseRow]:
        """Execute a query that returns rows."""
        if not self._connection:
            raise ConnectionError("Not connected to database")
        
        param_values = [p.value for p in params]
        cursor = await self._connection.execute(query, param_values)
        rows = await cursor.fetchall()
        
        # Convert to DatabaseRow objects
        result = []
        for row in rows:
            result.append(SqliteRow(row, cursor.description))
        
        return result
    
    async def query_one(self, query: str, params: List[DatabaseValue]) -> Optional[DatabaseRow]:
        """Execute a query that returns a single row."""
        if not self._connection:
            raise ConnectionError("Not connected to database")
        
        param_values = [p.value for p in params]
        cursor = await self._connection.execute(query, param_values)
        row = await cursor.fetchone()
        
        if row is None:
            return None
        
        return SqliteRow(row, cursor.description)
    
    async def begin_transaction(self) -> DatabaseTransaction:
        """Begin a transaction."""
        if not self._connection:
            raise ConnectionError("Not connected to database")
        return SqliteTransaction(self._connection)
    
    def get_database_type(self) -> DatabaseType:
        """Get the database type."""
        return DatabaseType.SQLITE
    
    async def ping(self) -> None:
        """Check if the connection is alive."""
        if not self._connection:
            raise ConnectionError("Not connected to database")
        
        # Simple query to check connection
        await self._connection.execute("SELECT 1")
    
    async def close(self) -> None:
        """Close the connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None


class SqliteTransaction(DatabaseTransaction):
    """SQLite transaction implementation."""
    
    def __init__(self, connection):
        self.connection = connection
        self._started = False
    
    async def _ensure_started(self):
        """Ensure transaction is started."""
        if not self._started:
            await self.connection.execute("BEGIN")
            self._started = True
    
    async def execute(self, query: str, params: List[DatabaseValue]) -> int:
        """Execute a query within the transaction that returns no rows."""
        await self._ensure_started()
        param_values = [p.value for p in params]
        cursor = await self.connection.execute(query, param_values)
        return cursor.rowcount
    
    async def query(self, query: str, params: List[DatabaseValue]) -> List[DatabaseRow]:
        """Execute a query within the transaction that returns rows."""
        await self._ensure_started()
        param_values = [p.value for p in params]
        cursor = await self.connection.execute(query, param_values)
        rows = await cursor.fetchall()
        
        result = []
        for row in rows:
            result.append(SqliteRow(row, cursor.description))
        
        return result
    
    async def query_one(self, query: str, params: List[DatabaseValue]) -> Optional[DatabaseRow]:
        """Execute a query within the transaction that returns a single row."""
        await self._ensure_started()
        param_values = [p.value for p in params]
        cursor = await self.connection.execute(query, param_values)
        row = await cursor.fetchone()
        
        if row is None:
            return None
        
        return SqliteRow(row, cursor.description)
    
    async def commit(self) -> None:
        """Commit the transaction."""
        if self._started:
            await self.connection.commit()
            self._started = False
    
    async def rollback(self) -> None:
        """Rollback the transaction."""
        if self._started:
            await self.connection.rollback()
            self._started = False


class SqliteRow(DatabaseRow):
    """SQLite row implementation."""
    
    def __init__(self, row_data: tuple, description: list):
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
        return bool(value)
    
    def get_bytes(self, column: str) -> bytes:
        """Get a column value as bytes."""
        value = self._get_value(column)
        if value is None:
            raise QueryError(f"Column '{column}' is NULL")
        if isinstance(value, bytes):
            return value
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
        except QueryError:
            return None
    
    def try_get_bytes(self, column: str) -> Optional[bytes]:
        """Try to get a column value as bytes."""
        try:
            value = self._get_value(column)
            if value is None:
                return None
            if isinstance(value, bytes):
                return value
            return str(value).encode('utf-8')
        except QueryError:
            return None


def _is_running_as_module() -> bool:
    """Check if running as a module under orchestrator."""
    return os.getenv("PYWATT_MODULE_ID") is not None


async def create_database_connection(config: DatabaseConfig) -> DatabaseConnection:
    """Create a database connection based on configuration."""
    # Check if we're running as a module (under orchestrator)
    if _is_running_as_module():
        # Create an IPC-based proxy connection
        return await ProxyDatabaseConnection.connect(config)
    
    # If not running as a module, use direct connections
    if config.db_type == DatabaseType.POSTGRES:
        try:
            from .postgresql import PostgresConnection
            return await PostgresConnection.connect(config)
        except ImportError:
            raise ConfigurationError(
                "PostgreSQL support requires asyncpg. Install with: pip install asyncpg"
            )
    elif config.db_type == DatabaseType.MYSQL:
        try:
            from .mysql import MySqlConnection
            return await MySqlConnection.connect(config)
        except ImportError:
            raise ConfigurationError(
                "MySQL support requires aiomysql. Install with: pip install aiomysql"
            )
    elif config.db_type == DatabaseType.SQLITE:
        return await SqliteConnection.connect(config)
    else:
        raise ConfigurationError(f"Unsupported database type: {config.db_type}")


class ProxyDatabaseTransaction(DatabaseTransaction):
    """Database transaction that proxies operations through the orchestrator."""
    
    def __init__(self, connection_id: str, transaction_id: str):
        self.connection_id = connection_id
        self.transaction_id = transaction_id
        self._committed = False
        self._rolled_back = False
    
    async def execute(self, query: str, params: List[DatabaseValue]) -> int:
        """Execute a query within the transaction via orchestrator proxy."""
        if self._committed or self._rolled_back:
            raise TransactionError("Transaction has already been committed or rolled back")
        
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        # Serialize parameters
        serialized_params = [self._serialize_param(p) for p in params]
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="transaction_execute",
            params={
                "transaction_id": self.transaction_id,
                "query": query,
                "params": serialized_params
            }
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise QueryError(f"Transaction execute failed: {result.get('error', 'Unknown error')}")
            
            return result.get("result", 0)
            
        except Exception as e:
            raise QueryError(f"Failed to execute query in transaction via proxy: {e}")
    
    async def query(self, query: str, params: List[DatabaseValue]) -> List[DatabaseRow]:
        """Execute a query within the transaction via orchestrator proxy."""
        if self._committed or self._rolled_back:
            raise TransactionError("Transaction has already been committed or rolled back")
        
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        # Serialize parameters
        serialized_params = [self._serialize_param(p) for p in params]
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="transaction_query",
            params={
                "transaction_id": self.transaction_id,
                "query": query,
                "params": serialized_params
            }
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise QueryError(f"Transaction query failed: {result.get('error', 'Unknown error')}")
            
            rows_data = result.get("result", [])
            return [ProxyDatabaseRow(row) for row in rows_data]
            
        except Exception as e:
            raise QueryError(f"Failed to execute query in transaction via proxy: {e}")
    
    async def query_one(self, query: str, params: List[DatabaseValue]) -> Optional[DatabaseRow]:
        """Execute a query within the transaction via orchestrator proxy."""
        if self._committed or self._rolled_back:
            raise TransactionError("Transaction has already been committed or rolled back")
        
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        # Serialize parameters
        serialized_params = [self._serialize_param(p) for p in params]
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="transaction_query_one",
            params={
                "transaction_id": self.transaction_id,
                "query": query,
                "params": serialized_params
            }
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise QueryError(f"Transaction query_one failed: {result.get('error', 'Unknown error')}")
            
            row_data = result.get("result")
            return ProxyDatabaseRow(row_data) if row_data else None
            
        except Exception as e:
            raise QueryError(f"Failed to execute query_one in transaction via proxy: {e}")
    
    async def commit(self) -> None:
        """Commit the transaction via orchestrator proxy."""
        if self._committed:
            raise TransactionError("Transaction has already been committed")
        if self._rolled_back:
            raise TransactionError("Transaction has already been rolled back")
        
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="transaction_commit",
            params={"transaction_id": self.transaction_id}
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise TransactionError(f"Transaction commit failed: {result.get('error', 'Unknown error')}")
            
            self._committed = True
            
        except Exception as e:
            raise TransactionError(f"Failed to commit transaction via proxy: {e}")
    
    async def rollback(self) -> None:
        """Rollback the transaction via orchestrator proxy."""
        if self._committed:
            raise TransactionError("Transaction has already been committed")
        if self._rolled_back:
            raise TransactionError("Transaction has already been rolled back")
        
        from ..communication.ipc_types import ServiceOperation, ServiceType
        from ..communication.ipc import send_ipc_message
        
        operation = ServiceOperation(
            connection_id=self.connection_id,
            service_type=ServiceType.DATABASE,
            operation="transaction_rollback",
            params={"transaction_id": self.transaction_id}
        )
        
        try:
            result = await send_ipc_message(operation)
            
            if not result.get("success", False):
                raise TransactionError(f"Transaction rollback failed: {result.get('error', 'Unknown error')}")
            
            self._rolled_back = True
            
        except Exception as e:
            raise TransactionError(f"Failed to rollback transaction via proxy: {e}")
    
    def _serialize_param(self, param: DatabaseValue) -> Any:
        """Serialize a DatabaseValue for IPC transmission."""
        if param.value is None:
            return None
        elif isinstance(param.value, (str, int, float, bool)):
            return param.value
        elif isinstance(param.value, bytes):
            import base64
            return base64.b64encode(param.value).decode('utf-8')
        elif isinstance(param.value, list):
            return [self._serialize_param(DatabaseValue(v)) for v in param.value]
        else:
            return str(param.value)


class ProxyDatabaseRow(DatabaseRow):
    """Database row implementation for proxy connections."""
    
    def __init__(self, data: Dict[str, Any]):
        self.data = data
    
    def get_string(self, column: str) -> str:
        """Get a string value from the row."""
        if column not in self.data:
            raise ValueError(f"Column '{column}' not found")
        
        value = self.data[column]
        if value is None:
            raise ValueError(f"Column '{column}' is NULL")
        
        if isinstance(value, str):
            return value
        else:
            raise ValueError(f"Column '{column}' is not a string")
    
    def get_int(self, column: str) -> int:
        """Get an integer value from the row."""
        if column not in self.data:
            raise ValueError(f"Column '{column}' not found")
        
        value = self.data[column]
        if value is None:
            raise ValueError(f"Column '{column}' is NULL")
        
        if isinstance(value, int):
            return value
        elif isinstance(value, float) and value.is_integer():
            return int(value)
        else:
            raise ValueError(f"Column '{column}' is not an integer")
    
    def get_float(self, column: str) -> float:
        """Get a float value from the row."""
        if column not in self.data:
            raise ValueError(f"Column '{column}' not found")
        
        value = self.data[column]
        if value is None:
            raise ValueError(f"Column '{column}' is NULL")
        
        if isinstance(value, (int, float)):
            return float(value)
        else:
            raise ValueError(f"Column '{column}' is not a number")
    
    def get_bool(self, column: str) -> bool:
        """Get a boolean value from the row."""
        if column not in self.data:
            raise ValueError(f"Column '{column}' not found")
        
        value = self.data[column]
        if value is None:
            raise ValueError(f"Column '{column}' is NULL")
        
        if isinstance(value, bool):
            return value
        elif isinstance(value, int):
            return bool(value)
        else:
            raise ValueError(f"Column '{column}' is not a boolean")
    
    def get_bytes(self, column: str) -> bytes:
        """Get a bytes value from the row."""
        if column not in self.data:
            raise ValueError(f"Column '{column}' not found")
        
        value = self.data[column]
        if value is None:
            raise ValueError(f"Column '{column}' is NULL")
        
        if isinstance(value, bytes):
            return value
        elif isinstance(value, str):
            # Assume base64 encoded
            import base64
            try:
                return base64.b64decode(value)
            except Exception:
                raise ValueError(f"Column '{column}' is not valid base64")
        else:
            raise ValueError(f"Column '{column}' is not bytes")
    
    def try_get_string(self, column: str) -> Optional[str]:
        """Try to get a string value from the row."""
        if column not in self.data:
            return None
        
        value = self.data[column]
        if value is None:
            return None
        
        if isinstance(value, str):
            return value
        else:
            raise ValueError(f"Column '{column}' is not a string")
    
    def try_get_int(self, column: str) -> Optional[int]:
        """Try to get an integer value from the row."""
        if column not in self.data:
            return None
        
        value = self.data[column]
        if value is None:
            return None
        
        if isinstance(value, int):
            return value
        elif isinstance(value, float) and value.is_integer():
            return int(value)
        else:
            raise ValueError(f"Column '{column}' is not an integer")
    
    def try_get_float(self, column: str) -> Optional[float]:
        """Try to get a float value from the row."""
        if column not in self.data:
            return None
        
        value = self.data[column]
        if value is None:
            return None
        
        if isinstance(value, (int, float)):
            return float(value)
        else:
            raise ValueError(f"Column '{column}' is not a number")
    
    def try_get_bool(self, column: str) -> Optional[bool]:
        """Try to get a boolean value from the row."""
        if column not in self.data:
            return None
        
        value = self.data[column]
        if value is None:
            return None
        
        if isinstance(value, bool):
            return value
        elif isinstance(value, int):
            return bool(value)
        else:
            raise ValueError(f"Column '{column}' is not a boolean")
    
    def try_get_bytes(self, column: str) -> Optional[bytes]:
        """Try to get a bytes value from the row."""
        if column not in self.data:
            return None
        
        value = self.data[column]
        if value is None:
            return None
        
        if isinstance(value, bytes):
            return value
        elif isinstance(value, str):
            # Assume base64 encoded
            import base64
            try:
                return base64.b64decode(value)
            except Exception:
                raise ValueError(f"Column '{column}' is not valid base64")
        else:
            raise ValueError(f"Column '{column}' is not bytes") 