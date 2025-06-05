# Model Manager Service (`pywatt_sdk::services::model_manager`)

This service provides a comprehensive toolkit for defining database schemas in Rust, generating SQL for various database systems, and integrating these management tasks directly with the PyWatt SDK's database connections.

## Core Concepts and Workflow

The Model Manager revolves around a few key ideas:

1.  **Schema Definition**: You define your database tables, columns, indexes, and constraints using Rust structs like `ModelDescriptor` and `ColumnDescriptor` provided in `definitions.rs`.
2.  **Database Abstraction**: The `DatabaseAdapter` trait (`adapters/trait_def.rs`) defines an interface for database-specific SQL generation. Concrete implementations exist for SQLite, PostgreSQL, and MySQL.
3.  **SQL Generation**: The `ModelGenerator` struct (`generator.rs`) takes a `ModelDescriptor` and a `DatabaseAdapter` to produce SQL strings for creating, dropping, or altering tables and their components.
4.  **SDK Integration**: The `ModelManager` trait (`sdk_integration.rs`) extends the SDK's `DatabaseConnection` trait. This allows you to directly apply model definitions to a live database connection, manage schema synchronization, and drop tables using high-level methods.
5.  **Configuration**: `ModelManagerConfig` (`config.rs`) helps in selecting and instantiating the correct `DatabaseAdapter` based on the target database type.

## Directory Structure

-   **`adapters/`**: Contains database-specific adapters.
    -   `mysql_adapter.rs`: MySQL specific SQL generation logic.
    -   `postgres_adapter.rs`: PostgreSQL specific SQL generation logic.
    -   `sqlite_adapter.rs`: SQLite specific SQL generation logic.
    -   `trait_def.rs`: Defines the `DatabaseAdapter` trait, the core interface for database-specific operations.
-   **`config.rs`**: Defines `ModelManagerConfig` used to configure and retrieve the appropriate `DatabaseAdapter` for a given `DatabaseType`.
-   **`definitions.rs`**: Contains all core data structures for defining database schemas (models, columns, data types, constraints, indexes).
-   **`errors.rs`**: Defines custom `Error` types for the model manager, providing specific contexts for failures (e.g., `SqlGenerationError`, `AdapterError`).
-   **`generator.rs`**: Contains the `ModelGenerator` struct, responsible for orchestrating SQL script generation using a `DatabaseAdapter`.
-   **`sdk_integration.rs`**: Defines the `ModelManager` trait, which extends `DatabaseConnection` to provide high-level schema management functions.
-   **`mod.rs`**: The main module file for `model_manager`, re-exporting key public types and submodules.
-   **`README.md`**: This file.

## Detailed Component Breakdown

### Schema Definition (`definitions.rs`)

These are the building blocks for describing your database structure:

-   **`ModelDescriptor`**: Represents a database table.
    -   Key fields: `name` (table name), `schema` (optional schema name), `columns` (Vec<ColumnDescriptor>), `primary_key` (optional composite PK), `indexes` (Vec<IndexDescriptor>), `constraints` (Vec<Constraint> for table-level constraints like multi-column unique or foreign keys).
-   **`ColumnDescriptor`**: Represents a column within a table.
    -   Key fields: `name`, `data_type` (DataType), `is_nullable`, `is_primary_key` (for single-column PK), `is_unique`, `default_value`, `auto_increment`, `constraints` (Vec<Constraint> for column-level constraints like `NotNull`).
-   **`DataType`**: An enum for common database types.
    -   Examples: `Text(Option<u32>)`, `Varchar(u32)`, `Integer(IntegerSize)`, `Boolean`, `Float`, `Double`, `Date`, `Time`, `DateTime`, `Timestamp`, `TimestampTz`, `Blob`, `Json`, `JsonB`, `Uuid`, `Enum(String, Vec<String>)`.
    -   `IntegerSize`: Enum (`I8` through `U64`) used with `DataType::Integer`.
-   **`Constraint`**: An enum defining various SQL constraints.
    -   Variants: `PrimaryKey { name, columns }`, `Unique { name, columns }`, `NotNull`, `DefaultValue(String)`, `Check { name, expression }`, `ForeignKey { name, columns, references_table, references_columns, on_delete, on_update }`.
    -   `ReferentialAction`: Enum (`NoAction`, `Restrict`, `Cascade`, `SetNull`, `SetDefault`) used with `ForeignKey` constraints.
-   **`IndexDescriptor`**: Represents a database index.
    -   Key fields: `name` (optional), `columns` (Vec<String>), `is_unique`, `index_type` (Option<IndexType>), `condition` (for partial indexes).
    -   `IndexType`: Enum (`BTree`, `Hash`, `Gin`, `Gist`, `Spatial`) for specifying index algorithms (database support varies).

### Database Abstraction (`adapters/trait_def.rs`)

-   **`DatabaseAdapter` trait**: Defines the contract for database-specific operations.
    -   Purpose: To translate abstract schema definitions (`ModelDescriptor`, `ColumnDescriptor`, etc.) and operations into concrete SQL syntax for a specific database engine (SQLite, PostgreSQL, MySQL).
    -   Key methods include:
        -   `get_db_type_name() -> &'static str`: Returns the name of the database (e.g., "sqlite").
        -   `map_common_data_type(common_type: &DataType) -> Result<String>`: Maps a `DataType` enum to a database-specific type string (e.g., `DataType::Integer(IntegerSize::I64)` to `"BIGINT"`).
        -   `generate_column_definition_sql(column: &ColumnDescriptor) -> Result<String>`: Generates the SQL fragment for a single column definition within a `CREATE TABLE` statement.
        -   `generate_constraint_sql(constraint: &Constraint, table_name: &str) -> Result<Option<String>>`: Generates SQL for a table-level or column-level constraint.
        -   `generate_create_table_sql(model: &ModelDescriptor) -> Result<String>`: Generates the full `CREATE TABLE` statement for a model.
        -   `generate_drop_table_sql(table_name: &str, schema_name: Option<&str>) -> Result<String>`.
        -   `generate_add_column_sql(...)`, `generate_drop_column_sql(...)`.
        -   `generate_index_sql(...)`, `generate_drop_index_sql(...)`.
        -   `generate_enum_types_sql(model: &ModelDescriptor) -> Result<Vec<String>>`: Generates `CREATE TYPE` statements for enums (primarily for PostgreSQL).
    -   Implementations: `SqliteAdapter`, `PostgresAdapter`, `MySqlAdapter` are provided in the `adapters` subdirectory.

### SQL Generation (`generator.rs`)

-   **`ModelGenerator` struct**:
    -   Purpose: Orchestrates the generation of SQL scripts by using a specific `DatabaseAdapter`.
    -   Constructor: `ModelGenerator::new(adapter: Box<dyn DatabaseAdapter<Error = Error>>)`.
    -   Key methods:
        -   `generate_create_table_script(model: &ModelDescriptor) -> Result<String>`: Generates a complete script to create a table, including column definitions, primary keys, inline constraints, and separate `CREATE INDEX` statements. For databases like PostgreSQL, it also includes necessary `CREATE TYPE` statements for enums defined in the model, ensuring they are created before the table.
        -   `generate_drop_table_script(table_name: &str, schema_name: Option<&str>) -> Result<String>`.
        -   `generate_add_column_script(...)`, `generate_drop_column_script(...)`.
        -   `generate_foreign_key_script(table_name: &str, fk: &Constraint) -> Result<String>`.
        -   `generate_migration_script(from: &ModelDescriptor, to: &ModelDescriptor) -> Result<String>`: Generates an SQL script to transform an existing table schema (`from`) to a new schema (`to`). This includes adding/dropping columns, adding/dropping constraints, and adding/dropping indexes. This is useful for more complex schema evolutions.

### SDK Integration (`sdk_integration.rs`)

-   **`ModelManager` trait**:
    -   Purpose: Extends the `pywatt_sdk::data::database::DatabaseConnection` trait to provide high-level, direct database schema manipulation capabilities.
    -   It uses an appropriate `DatabaseAdapter` (obtained via `ModelManagerConfig` or internally based on the connection type) and the `ModelGenerator` to execute schema changes.
    -   Key methods (available on types implementing `DatabaseConnection` when the `database` feature is enabled):
        -   `async fn apply_model(&mut self, model: &ModelDescriptor) -> DatabaseResult<()>`: Attempts to create the table and its associated objects (enums, indexes) as defined by the `ModelDescriptor`. It's designed to be somewhat idempotent; for example, if an enum type or index already exists, it typically won't error. However, if the `CREATE TABLE` statement itself fails because the table already exists, this method will return that specific error, which `sync_schema` can then interpret.
        -   `async fn drop_model(&mut self, table_name: &str, schema_name: Option<&str>) -> DatabaseResult<()>`: Drops the specified table from the database.
        -   `async fn sync_schema(&mut self, models: &[ModelDescriptor]) -> DatabaseResult<()>`: Aims to synchronize the database schema with the provided list of `ModelDescriptor`s. For each model:
            1.  It first attempts to call `apply_model`.
            2.  If `apply_model` fails with an error indicating the table *already exists*, `sync_schema` currently performs a simplified migration: it tries to identify and add any columns present in the `ModelDescriptor` but missing from the existing table. (Note: It does not yet perform full diffing and complex migrations like altering column types or dropping/modifying existing constraints/indexes through this path; for more complex migrations, use `ModelGenerator::generate_migration_script` and execute it manually).
            3.  Other errors from `apply_model` are propagated.

### Configuration (`config.rs`)

-   **`ModelManagerConfig` struct**:
    -   Fields: `database_type: DatabaseType` (from `pywatt_sdk::data::database`).
    -   Method: `get_adapter(&self) -> Result<Box<dyn DatabaseAdapter<Error = Error>>>`: Returns an instance of the appropriate `DatabaseAdapter` (e.g., `SqliteAdapter`, `PostgresAdapter`) based on the `database_type`.

### Error Handling (`errors.rs`)

-   **`Error` enum**: Provides specific error types for operations within the model manager, such as `SqlGenerationError(String)`, `AdapterError(String)`, `DefinitionError(String)`. This allows for more granular error handling compared to a generic database error.

## Example Usage

### Defining a Model

```rust
use pywatt_sdk::services::model_manager::{
    ModelDescriptor, ColumnDescriptor, DataType, IntegerSize, Constraint, IndexDescriptor, IndexType, ReferentialAction
};

fn get_user_model() -> ModelDescriptor {
    ModelDescriptor {
        name: "users".to_string(),
        schema: Some("public".to_string()), // Optional schema
        columns: vec![
            ColumnDescriptor {
                name: "id".to_string(),
                data_type: DataType::Integer(IntegerSize::I64),
                is_primary_key: true, // Marks as part of PK, for single col PK
                auto_increment: true,
                is_nullable: false,
                ..Default::default()
            },
            ColumnDescriptor {
                name: "username".to_string(),
                data_type: DataType::Varchar(255),
                is_unique: true, // Creates a unique constraint for this column
                is_nullable: false,
                ..Default::default()
            },
            ColumnDescriptor {
                name: "email".to_string(),
                data_type: DataType::Varchar(255),
                is_nullable: false,
                constraints: vec![Constraint::Unique { name: Some("uq_email".to_string()), columns: vec!["email".to_string()]}],
                ..Default::default()
            },
            ColumnDescriptor {
                name: "role_id".to_string(),
                data_type: DataType::Integer(IntegerSize::I32),
                is_nullable: true,
                ..Default::default()
            },
            ColumnDescriptor {
                name: "created_at".to_string(),
                data_type: DataType::TimestampTz,
                is_nullable: false,
                default_value: Some("CURRENT_TIMESTAMP".to_string()),
                ..Default::default()
            },
        ],
        indexes: vec![
            IndexDescriptor {
                name: Some("idx_username".to_string()),
                columns: vec!["username".to_string()],
                is_unique: false, // Can create non-unique indexes too
                index_type: Some(IndexType::BTree),
                ..Default::default()
            }
        ],
        constraints: vec![ // Table-level constraints
            Constraint::ForeignKey {
                name: Some("fk_user_role".to_string()),
                columns: vec!["role_id".to_string()],
                references_table: "roles".to_string(),
                references_columns: vec!["id".to_string()],
                on_delete: Some(ReferentialAction::SetNull),
                on_update: Some(ReferentialAction::Cascade),
            }
        ],
        comment: Some("Stores user account information".to_string()),
        ..Default::default()
    }
}

fn get_role_model() -> ModelDescriptor {
    ModelDescriptor {
        name: "roles".to_string(),
        schema: Some("public".to_string()),
        columns: vec![
            ColumnDescriptor {
                name: "id".to_string(),
                data_type: DataType::Integer(IntegerSize::I32),
                is_primary_key: true,
                auto_increment: true,
                is_nullable: false,
                ..Default::default()
            },
            ColumnDescriptor {
                name: "name".to_string(),
                data_type: DataType::Varchar(50),
                is_unique: true,
                is_nullable: false,
                ..Default::default()
            },
        ],
        ..Default::default()
    }
}
```

### Generating SQL Scripts with `ModelGenerator`

```rust
use pywatt_sdk::services::model_manager::{ModelGenerator, ModelManagerConfig, ModelDescriptor, ColumnDescriptor, DataType, IntegerSize};
use pywatt_sdk::data::database::DatabaseType;
// Assuming get_user_model() is defined as above

fn generate_scripts() -> Result<(), pywatt_sdk::services::model_manager::Error> {
    let config = ModelManagerConfig::new(DatabaseType::Postgres);
    let adapter = config.get_adapter()?;
    let generator = ModelGenerator::new(adapter);
    
    let user_model = get_user_model();

    // Generate CREATE TABLE script
    let create_sql = generator.generate_create_table_script(&user_model)?;
    println!("--- CREATE TABLE SQL (users) ---\n{}", create_sql);

    // Generate DROP TABLE script
    let drop_sql = generator.generate_drop_table_script(&user_model.name, user_model.schema.as_deref())?;
    println!("--- DROP TABLE SQL (users) ---\n{}", drop_sql);

    // Generate a migration script (example: adding a 'last_login' column)
    let mut user_model_v2 = user_model.clone();
    user_model_v2.columns.push(ColumnDescriptor {
        name: "last_login".to_string(),
        data_type: DataType::TimestampTz,
        is_nullable: true,
        ..Default::default()
    });
    let migration_sql = generator.generate_migration_script(&user_model, &user_model_v2)?;
    println!("--- MIGRATION SQL (users to users_v2) ---\n{}", migration_sql);

    Ok(())
}
// To run: if let Err(e) = generate_scripts() { eprintln!("Error: {}", e); }
```

### Applying Models and Syncing Schema with `ModelManager` Trait

(Requires `database` feature enabled for `pywatt_sdk`)
```rust
# #[cfg(feature = "database")]
# async fn db_operations() -> Result<(), Box<dyn std::error::Error>> {
use pywatt_sdk::services::model_manager::{ModelManager, ModelDescriptor};
use pywatt_sdk::data::database::{DatabasePool, DatabaseConfig, DatabaseType, DatabaseConnection}; // Assuming DatabasePool and DatabaseConfig are available
// Assuming get_user_model() and get_role_model() are defined as above

// Dummy DatabasePool for example purposes
# let config = DatabaseConfig::new(DatabaseType::Sqlite, ":memory:".to_string(), None, None, None, None, Default::default())?;
# let pool = DatabasePool::new(config).await?;

// 1. Apply a single model
async fn apply_single_model(pool: &DatabasePool) -> Result<(), pywatt_sdk::data::database::DatabaseError> {
    let mut conn = pool.get_connection().await?;
    let user_model = get_user_model();
    conn.apply_model(&user_model).await?;
    println!("User model applied successfully.");
    Ok(())
}

// 2. Synchronize multiple models with the schema
async fn sync_all_models(pool: &DatabasePool) -> Result<(), pywatt_sdk::data::database::DatabaseError> {
    let mut conn = pool.get_connection().await?;
    let models_to_sync = vec![get_role_model(), get_user_model()]; // Order matters for FKs if tables are new
    
    // First, ensure roles table exists if users depends on it
    // conn.apply_model(&get_role_model()).await.ok(); // .ok() to ignore if already exists or other errors for this simple setup

    conn.sync_schema(&models_to_sync).await?;
    println!("All models synchronized with the database schema.");
    
    // Example of how sync_schema handles existing tables with missing columns:
    let mut user_model_v2 = get_user_model();
    user_model_v2.columns.push(pywatt_sdk::services::model_manager::ColumnDescriptor {
        name: "bio".to_string(),
        data_type: pywatt_sdk::services::model_manager::DataType::Text(None),
        is_nullable: true,
        ..Default::default()
    });
    // If 'users' table exists but 'bio' column is missing, sync_schema will add it.
    conn.sync_schema(&[user_model_v2]).await?;
    println!("User model (v2 with bio) synchronized.");

    Ok(())
}

// To run (example):
// if let Err(e) = apply_single_model(&pool).await { eprintln!("Apply error: {}", e); }
// if let Err(e) = sync_all_models(&pool).await { eprintln!("Sync error: {}", e); }
# Ok(())
# }
```

## See Also

-   [Main Services README](../README.md)
-   Source files in this directory for complete implementation details.
-   `pywatt_sdk::data::database` for `DatabaseConnection` and related types.
