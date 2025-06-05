# Database Module

This module provides a unified interface for interacting with various SQL database systems, along with mechanisms for connection pooling, transaction management, and configuration. It also supports connecting to a remote database service via IPC.

## Core Components

The `database` module is built around several key traits, structs, and enums:

-   **`DatabaseConnection` Trait**: Defines the primary asynchronous interface for database interactions. Implementations of this trait provide methods for executing queries (`execute`, `query`, `query_one`), managing transactions (`begin_transaction`), and obtaining database metadata (`get_database_type`).
-   **`DatabaseTransaction` Trait**: Represents an atomic database transaction. It provides methods for executing queries within the transaction (`execute`, `query`, `query_one`) and for committing (`commit`) or rolling back (`rollback`) the transaction.
-   **`DatabaseRow` Trait**: An interface for accessing data from a single row returned by a query. It offers methods to retrieve values by column name, converting them to various Rust types (e.g., `get_string`, `get_i64`, `try_get_bool`).
-   **`DatabaseConfig` Struct**: Used to configure database connections. It includes fields for the database type, connection parameters (host, port, database name, credentials), SSL settings, and connection pool settings.
-   **`PoolConfig` Struct**: Specifies settings for the connection pool, such as maximum/minimum connections, idle timeout, and connection lifetime.
-   **`DatabaseType` Enum**: An enumeration of supported database systems: `Postgres`, `MySql`, and `Sqlite`.
-   **`DatabaseError` Enum**: Represents various errors that can occur during database operations, such as connection errors, query errors, or configuration issues.
-   **`DatabaseValue` Enum**: Represents different data types that can be used as parameters in database queries.
-   **`create_database_connection()` Function**: A factory function that takes a `DatabaseConfig` and returns a `DatabaseResult<Box<dyn DatabaseConnection>>`. This is the primary way to obtain a database connection instance.

## Implementations

The SDK provides several implementations for `DatabaseConnection`:

-   **PostgreSQL (`PostgresConnection`)**: Enabled by the `postgres` feature flag. Uses the `sqlx` crate for asynchronous communication with a PostgreSQL server. Found in `postgres.rs`.
-   **MySQL (`MySqlConnection`)**: Enabled by the `mysql` feature flag. Uses the `sqlx` crate for asynchronous communication with a MySQL server. Found in `mysql.rs`.
-   **SQLite (`SqliteConnection`)**: Enabled by the `sqlite` feature flag. Uses the `sqlx` crate for asynchronous interaction with a SQLite database (file-based or in-memory). Found in `sqlite.rs`.
-   **Proxy Connection (`ProxyDatabaseConnection`)**: This implementation (in `proxy_connection.rs`) allows the SDK to act as a client to a remote database service. It translates `DatabaseConnection` calls into IPC messages, sends them to an orchestrator or a dedicated database service, and processes the responses. This is useful in distributed architectures where direct database access from a module might not be available or desired.

## Usage

### 1. Configuration

First, create a `DatabaseConfig` instance:

```rust
use pywatt_sdk::data::database::{DatabaseConfig, DatabaseType, PoolConfig};

// Example for PostgreSQL
let pg_config = DatabaseConfig {
    db_type: DatabaseType::Postgres,
    host: Some("localhost".to_string()),
    port: Some(5432),
    database: "mydatabase".to_string(),
    username: Some("user".to_string()),
    password: Some("password".to_string()),
    ssl_mode: Some("prefer".to_string()),
    pool: PoolConfig::default(),
    extra_params: Default::default(),
};

// Example for SQLite (in-memory)
let sqlite_config = DatabaseConfig {
    db_type: DatabaseType::Sqlite,
    database: ":memory:".to_string(),
    ..Default::default() // Uses defaults for other fields
};
```

Helper functions like `postgres_config()`, `mysql_config()`, and `sqlite_config()` are also available in `data::database::mod_rs` for easier configuration struct creation.

### 2. Creating a Connection

Use the `create_database_connection` function:

```rust
use pywatt_sdk::data::database::{create_database_connection, DatabaseConfig, DatabaseType};
# async fn example() -> Result<(), Box<dyn std::error::Error>> {
# let config = DatabaseConfig { db_type: DatabaseType::Sqlite, database: ":memory:".to_string(), ..Default::default() };
let connection = create_database_connection(&config).await?;
# Ok(())
# }
```

### 3. Executing Queries

```rust
use pywatt_sdk::data::database::{DatabaseValue, DatabaseConnection};
# async fn example(connection: Box<dyn DatabaseConnection>) -> Result<(), Box<dyn std::error::Error>> {
// Execute a query that returns no rows (e.g., INSERT, UPDATE, DELETE)
let rows_affected = connection.execute(
    "INSERT INTO users (name, email) VALUES ($1, $2)",
    &[DatabaseValue::Text("Alice".to_string()), DatabaseValue::Text("alice@example.com".to_string())]
).await?;
println!("Rows affected: {}", rows_affected);

// Execute a query that returns rows
let rows = connection.query("SELECT id, name FROM users WHERE name = $1", &[DatabaseValue::Text("Alice".to_string())]).await?;
for row in rows {
    let id: i64 = row.get_i64("id")?;
    let name: String = row.get_string("name")?;
    println!("User ID: {}, Name: {}", id, name);
}
# Ok(())
# }
```

### 4. Using Transactions

```rust
use pywatt_sdk::data::database::{DatabaseValue, DatabaseConnection, DatabaseTransaction};
# async fn example(connection: Box<dyn DatabaseConnection>) -> Result<(), Box<dyn std::error::Error>> {
let mut transaction = connection.begin_transaction().await?;

transaction.execute("INSERT INTO logs (message) VALUES ($1)", &[DatabaseValue::Text("Log entry 1".to_string())]).await?;
transaction.execute("INSERT INTO logs (message) VALUES ($1)", &[DatabaseValue::Text("Log entry 2".to_string())]).await?;

// Commit the transaction
transaction.commit().await?;
# Ok(())
# }
```

## Feature Flags

Specific database backend implementations are enabled via Cargo feature flags:

-   `postgres`: Enables PostgreSQL support (`PostgresConnection`).
-   `mysql`: Enables MySQL support (`MySqlConnection`).
-   `sqlite`: Enables SQLite support (`SqliteConnection`).

If none of these features are enabled, only the `ProxyDatabaseConnection` might be available, depending on how the SDK is used or configured by an orchestrator.

## Error Handling

All fallible operations within this module return a `DatabaseResult<T>`, which is an alias for `Result<T, DatabaseError>`. The `DatabaseError` enum provides variants for different types of database-related issues.
