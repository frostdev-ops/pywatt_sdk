// PyWatt SDK - Database Model Manager
//
// This module provides database-agnostic model definition and
// schema generation tools for SQL databases.

pub mod adapters;
#[cfg(feature = "database")]
pub mod config;
pub mod definitions;
pub mod errors;
pub mod generator;
pub mod sdk_integration;

#[cfg(all(test, feature = "integration_tests"))]
pub mod integration_tests;

// Re-export core types for convenience
pub use adapters::DatabaseAdapter;
#[cfg(feature = "database")]
pub use config::ModelManagerConfig;
pub use definitions::{
    ColumnDescriptor, Constraint, DataType, IndexDescriptor, IndexType, IntegerSize,
    ModelDescriptor, ReferentialAction,
};
pub use errors::{Error, Result};
pub use generator::ModelGenerator;
pub use sdk_integration::ModelManager;

// Public API functions are defined below


// Import adapter implementations
use adapters::{MySqlAdapter, PostgresAdapter, SqliteAdapter};

// Public API functions

/// Get a database adapter for the specified database type.
/// 
/// This function returns a boxed trait object that implements the `DatabaseAdapter`
/// trait for the specified database type. The adapter can be used with `ModelGenerator`
/// to generate database-specific SQL statements.
/// 
/// # Arguments
/// * `db_type` - The database type to get an adapter for
/// 
/// # Returns
/// A boxed `DatabaseAdapter` implementation for the specified database type
/// 
/// # Examples
/// ```rust
/// use pywatt_sdk::model_manager::get_adapter_for_database_type;
/// use pywatt_sdk::data::database::DatabaseType;
/// 
/// let adapter = get_adapter_for_database_type(DatabaseType::Postgres);
/// // Use the adapter with ModelGenerator
/// ```
#[cfg(feature = "database")]
pub fn get_adapter_for_database_type(
    db_type: crate::data::database::DatabaseType,
) -> Box<dyn DatabaseAdapter<Error = Error>> {
    use crate::data::database::DatabaseType;
    
    match db_type {
        DatabaseType::Sqlite => Box::new(SqliteAdapter::new()),
        DatabaseType::Postgres => Box::new(PostgresAdapter::new()),
        DatabaseType::MySql => Box::new(MySqlAdapter::new()),
    }
}

/// Get a database adapter for the specified database type (non-database feature version).
/// 
/// This is a stub implementation for when the database feature is not enabled.
/// It will always return an error indicating that database features are not available.
#[cfg(not(feature = "database"))]
pub fn get_adapter_for_database_type(
    _db_type: &str,
) -> Result<Box<dyn DatabaseAdapter<Error = Error>>> {
    Err(Error::UnsupportedFeature(
        "Database features not enabled. Enable the 'database' feature to use this function.".to_string()
    ))
}

/// Create a new `ModelGenerator` for the specified database type.
/// 
/// This is a convenience function that combines `get_adapter_for_database_type`
/// and `ModelGenerator::new` into a single call.
/// 
/// # Arguments
/// * `db_type` - The database type to create a generator for
/// 
/// # Returns
/// A `ModelGenerator` configured for the specified database type
/// 
/// # Examples
/// ```rust
/// use pywatt_sdk::model_manager::create_generator_for_database;
/// use pywatt_sdk::data::database::DatabaseType;
/// 
/// let generator = create_generator_for_database(DatabaseType::Postgres);
/// ```
#[cfg(feature = "database")]
pub fn create_generator_for_database(
    db_type: crate::data::database::DatabaseType,
) -> ModelGenerator {
    let adapter = get_adapter_for_database_type(db_type);
    ModelGenerator::new(adapter)
}

/// Validate a model descriptor for common issues.
/// 
/// This function performs basic validation on a model descriptor to catch
/// common configuration errors before attempting to generate SQL or apply
/// the model to a database.
/// 
/// # Arguments
/// * `model` - The model descriptor to validate
/// 
/// # Returns
/// `Ok(())` if the model is valid, or an `Error` describing the validation issue
/// 
/// # Examples
/// ```rust
/// use pywatt_sdk::model_manager::{validate_model, ModelDescriptor};
/// 
/// let model = ModelDescriptor {
///     // ... model definition
/// #   name: "test".to_string(),
/// #   schema: None,
/// #   columns: vec![],
/// #   primary_key: None,
/// #   indexes: vec![],
/// #   constraints: vec![],
/// #   comment: None,
/// #   engine: None,
/// #   charset: None,
/// #   collation: None,
/// #   options: Default::default(),
/// };
/// 
/// validate_model(&model)?;
/// # Ok::<(), pywatt_sdk::model_manager::Error>(())
/// ```
pub fn validate_model(model: &ModelDescriptor) -> Result<()> {
    // Check that table name is not empty
    if model.name.trim().is_empty() {
        return Err(Error::ModelDefinition(
            "Table name cannot be empty".to_string()
        ));
    }
    
    // Check that there is at least one column
    if model.columns.is_empty() {
        return Err(Error::ModelDefinition(
            "Model must have at least one column".to_string()
        ));
    }
    
    // Check for duplicate column names
    let mut column_names = std::collections::HashSet::new();
    for column in &model.columns {
        if column.name.trim().is_empty() {
            return Err(Error::ModelDefinition(
                "Column name cannot be empty".to_string()
            ));
        }
        
        if !column_names.insert(&column.name) {
            return Err(Error::ModelDefinition(
                format!("Duplicate column name: {}", column.name)
            ));
        }
    }
    
    // Check primary key configuration
    let pk_columns_from_flags: Vec<&str> = model.columns
        .iter()
        .filter(|c| c.is_primary_key)
        .map(|c| c.name.as_str())
        .collect();
    
    if let Some(pk_columns) = &model.primary_key {
        if !pk_columns_from_flags.is_empty() {
            return Err(Error::ModelDefinition(
                "Cannot specify both table-level primary key and column-level primary key flags".to_string()
            ));
        }
        
        // Verify all PK columns exist
        for pk_col in pk_columns {
            if !model.columns.iter().any(|c| &c.name == pk_col) {
                return Err(Error::ModelDefinition(
                    format!("Primary key column '{}' does not exist in table", pk_col)
                ));
            }
        }
    }
    
    // Check auto-increment constraints
    let auto_increment_columns: Vec<&ColumnDescriptor> = model.columns
        .iter()
        .filter(|c| c.auto_increment)
        .collect();
    
    if auto_increment_columns.len() > 1 {
        return Err(Error::ModelDefinition(
            "Only one column can have auto_increment enabled".to_string()
        ));
    }
    
    if let Some(auto_col) = auto_increment_columns.first() {
        if !auto_col.is_primary_key && model.primary_key.as_ref().map_or(true, |pk| !pk.contains(&auto_col.name)) {
            return Err(Error::ModelDefinition(
                "Auto-increment column must be part of the primary key".to_string()
            ));
        }
        
        // Check that auto-increment column is an integer type
        match &auto_col.data_type {
            DataType::Integer(_) | DataType::SmallInt | DataType::BigInt => {
                // Valid
            }
            _ => {
                return Err(Error::ModelDefinition(
                    "Auto-increment column must be an integer type".to_string()
                ));
            }
        }
    }
    
    // Validate foreign key constraints
    for constraint in &model.constraints {
        if let Constraint::ForeignKey { columns, references_columns, .. } = constraint {
            if columns.len() != references_columns.len() {
                return Err(Error::ModelDefinition(
                    "Foreign key must have the same number of columns as referenced columns".to_string()
                ));
            }
            
            // Verify all FK columns exist
            for fk_col in columns {
                if !model.columns.iter().any(|c| &c.name == fk_col) {
                    return Err(Error::ModelDefinition(
                        format!("Foreign key column '{}' does not exist in table", fk_col)
                    ));
                }
            }
        }
    }
    
    // Validate index definitions
    for index in &model.indexes {
        if index.columns.is_empty() {
            return Err(Error::ModelDefinition(
                "Index must specify at least one column".to_string()
            ));
        }
        
        // Verify all index columns exist
        for idx_col in &index.columns {
            if !model.columns.iter().any(|c| &c.name == idx_col) {
                return Err(Error::ModelDefinition(
                    format!("Index column '{}' does not exist in table", idx_col)
                ));
            }
        }
    }
    
    Ok(())
}

/// Generate a complete SQL script for creating a model and all its associated objects.
/// 
/// This function generates SQL for creating enum types (PostgreSQL), the table itself,
/// and all indexes defined in the model. It's a convenience function that combines
/// multiple generator calls.
/// 
/// # Arguments
/// * `model` - The model descriptor to generate SQL for
/// * `db_type` - The target database type
/// 
/// # Returns
/// A complete SQL script as a string
/// 
/// # Examples
/// ```rust
/// use pywatt_sdk::model_manager::{generate_complete_sql, ModelDescriptor};
/// use pywatt_sdk::data::database::DatabaseType;
/// 
/// let model = ModelDescriptor {
///     // ... model definition
/// #   name: "test".to_string(),
/// #   schema: None,
/// #   columns: vec![],
/// #   primary_key: None,
/// #   indexes: vec![],
/// #   constraints: vec![],
/// #   comment: None,
/// #   engine: None,
/// #   charset: None,
/// #   collation: None,
/// #   options: Default::default(),
/// };
/// 
/// let sql = generate_complete_sql(&model, DatabaseType::Postgres)?;
/// # Ok::<(), pywatt_sdk::model_manager::Error>(())
/// ```
#[cfg(feature = "database")]
pub fn generate_complete_sql(
    model: &ModelDescriptor,
    db_type: crate::data::database::DatabaseType,
) -> Result<String> {
    // Validate the model first
    validate_model(model)?;
    
    let generator = create_generator_for_database(db_type);
    let mut script = String::new();
    
    // Generate enum types for PostgreSQL
    if matches!(db_type, crate::data::database::DatabaseType::Postgres) {
        if let Ok(enum_stmts) = generator.adapter().generate_enum_types_sql(model) {
            for stmt in enum_stmts {
                script.push_str(&stmt);
                script.push_str(";\n\n");
            }
        }
    }
    
    // Generate the main table creation script
    let table_script = generator.generate_create_table_script(model)?;
    script.push_str(&table_script);
    
    Ok(script)
}

/// Create a simple model with basic columns for common use cases.
/// 
/// This is a convenience function for creating models with standard patterns
/// like auto-incrementing ID, timestamps, etc.
/// 
/// # Arguments
/// * `table_name` - The name of the table
/// * `schema_name` - Optional schema name
/// 
/// # Returns
/// A `ModelBuilder` for further customization
/// 
/// # Examples
/// ```rust
/// use pywatt_sdk::model_manager::create_simple_model;
/// 
/// let model = create_simple_model("users", None)
///     .add_varchar_column("username", 100, false, true)
///     .add_varchar_column("email", 255, false, true)
///     .add_timestamp_column("created_at", false, Some("CURRENT_TIMESTAMP"))
///     .build();
/// ```
pub fn create_simple_model(table_name: &str, schema_name: Option<&str>) -> ModelBuilder {
    ModelBuilder::new(table_name, schema_name)
        .add_id_column() // Add standard auto-incrementing ID column
}

/// Builder pattern for creating model descriptors.
/// 
/// This provides a fluent API for building complex model definitions
/// with validation and sensible defaults.
pub struct ModelBuilder {
    model: ModelDescriptor,
}

impl ModelBuilder {
    /// Create a new model builder.
    pub fn new(table_name: &str, schema_name: Option<&str>) -> Self {
        Self {
            model: ModelDescriptor {
                name: table_name.to_string(),
                schema: schema_name.map(|s| s.to_string()),
                columns: Vec::new(),
                primary_key: None,
                indexes: Vec::new(),
                constraints: Vec::new(),
                comment: None,
                engine: None,
                charset: None,
                collation: None,
                options: Default::default(),
            },
        }
    }
    
    /// Add a standard auto-incrementing ID column.
    pub fn add_id_column(mut self) -> Self {
        self.model.columns.push(ColumnDescriptor {
            name: "id".to_string(),
            data_type: DataType::Integer(IntegerSize::I64),
            is_nullable: false,
            is_primary_key: true,
            is_unique: false,
            default_value: None,
            auto_increment: true,
            comment: Some("Primary key".to_string()),
            constraints: Vec::new(),
        });
        self
    }
    
    /// Add a VARCHAR column.
    pub fn add_varchar_column(
        mut self,
        name: &str,
        length: u32,
        nullable: bool,
        unique: bool,
    ) -> Self {
        self.model.columns.push(ColumnDescriptor {
            name: name.to_string(),
            data_type: DataType::Varchar(length),
            is_nullable: nullable,
            is_primary_key: false,
            is_unique: unique,
            default_value: None,
            auto_increment: false,
            comment: None,
            constraints: Vec::new(),
        });
        self
    }
    
    /// Add a TEXT column.
    pub fn add_text_column(mut self, name: &str, nullable: bool) -> Self {
        self.model.columns.push(ColumnDescriptor {
            name: name.to_string(),
            data_type: DataType::Text(None),
            is_nullable: nullable,
            is_primary_key: false,
            is_unique: false,
            default_value: None,
            auto_increment: false,
            comment: None,
            constraints: Vec::new(),
        });
        self
    }
    
    /// Add an integer column.
    pub fn add_integer_column(
        mut self,
        name: &str,
        size: IntegerSize,
        nullable: bool,
        unique: bool,
    ) -> Self {
        self.model.columns.push(ColumnDescriptor {
            name: name.to_string(),
            data_type: DataType::Integer(size),
            is_nullable: nullable,
            is_primary_key: false,
            is_unique: unique,
            default_value: None,
            auto_increment: false,
            comment: None,
            constraints: Vec::new(),
        });
        self
    }
    
    /// Add a boolean column.
    pub fn add_boolean_column(
        mut self,
        name: &str,
        nullable: bool,
        default_value: Option<bool>,
    ) -> Self {
        self.model.columns.push(ColumnDescriptor {
            name: name.to_string(),
            data_type: DataType::Boolean,
            is_nullable: nullable,
            is_primary_key: false,
            is_unique: false,
            default_value: default_value.map(|v| if v { "true".to_string() } else { "false".to_string() }),
            auto_increment: false,
            comment: None,
            constraints: Vec::new(),
        });
        self
    }
    
    /// Add a timestamp column.
    pub fn add_timestamp_column(
        mut self,
        name: &str,
        nullable: bool,
        default_value: Option<&str>,
    ) -> Self {
        self.model.columns.push(ColumnDescriptor {
            name: name.to_string(),
            data_type: DataType::TimestampTz,
            is_nullable: nullable,
            is_primary_key: false,
            is_unique: false,
            default_value: default_value.map(|s| s.to_string()),
            auto_increment: false,
            comment: None,
            constraints: Vec::new(),
        });
        self
    }
    
    /// Add a JSON column.
    pub fn add_json_column(mut self, name: &str, nullable: bool) -> Self {
        self.model.columns.push(ColumnDescriptor {
            name: name.to_string(),
            data_type: DataType::Json,
            is_nullable: nullable,
            is_primary_key: false,
            is_unique: false,
            default_value: None,
            auto_increment: false,
            comment: None,
            constraints: Vec::new(),
        });
        self
    }
    
    /// Add a UUID column.
    pub fn add_uuid_column(mut self, name: &str, nullable: bool, unique: bool) -> Self {
        self.model.columns.push(ColumnDescriptor {
            name: name.to_string(),
            data_type: DataType::Uuid,
            is_nullable: nullable,
            is_primary_key: false,
            is_unique: unique,
            default_value: None,
            auto_increment: false,
            comment: None,
            constraints: Vec::new(),
        });
        self
    }
    
    /// Add an enum column.
    pub fn add_enum_column(
        mut self,
        name: &str,
        enum_name: &str,
        variants: Vec<String>,
        nullable: bool,
    ) -> Self {
        self.model.columns.push(ColumnDescriptor {
            name: name.to_string(),
            data_type: DataType::Enum(enum_name.to_string(), variants),
            is_nullable: nullable,
            is_primary_key: false,
            is_unique: false,
            default_value: None,
            auto_increment: false,
            comment: None,
            constraints: Vec::new(),
        });
        self
    }
    
    /// Add standard created_at and updated_at timestamp columns.
    pub fn add_timestamps(self) -> Self {
        self.add_timestamp_column("created_at", false, Some("CURRENT_TIMESTAMP"))
            .add_timestamp_column("updated_at", false, Some("CURRENT_TIMESTAMP"))
    }
    
    /// Add an index on the specified columns.
    pub fn add_index(mut self, columns: Vec<String>, unique: bool) -> Self {
        self.model.indexes.push(IndexDescriptor {
            name: None, // Will be auto-generated
            columns,
            is_unique: unique,
            index_type: None,
            condition: None,
        });
        self
    }
    
    /// Add a named index on the specified columns.
    pub fn add_named_index(
        mut self,
        name: &str,
        columns: Vec<String>,
        unique: bool,
    ) -> Self {
        self.model.indexes.push(IndexDescriptor {
            name: Some(name.to_string()),
            columns,
            is_unique: unique,
            index_type: None,
            condition: None,
        });
        self
    }
    
    /// Add a foreign key constraint.
    pub fn add_foreign_key(
        mut self,
        columns: Vec<String>,
        references_table: &str,
        references_columns: Vec<String>,
        on_delete: Option<ReferentialAction>,
        on_update: Option<ReferentialAction>,
    ) -> Self {
        self.model.constraints.push(Constraint::ForeignKey {
            name: None, // Will be auto-generated
            columns,
            references_table: references_table.to_string(),
            references_columns,
            on_delete,
            on_update,
        });
        self
    }
    
    /// Add a unique constraint on multiple columns.
    pub fn add_unique_constraint(mut self, columns: Vec<String>) -> Self {
        self.model.constraints.push(Constraint::Unique {
            name: None, // Will be auto-generated
            columns,
        });
        self
    }
    
    /// Set the table comment.
    pub fn with_comment(mut self, comment: &str) -> Self {
        self.model.comment = Some(comment.to_string());
        self
    }
    
    /// Set the storage engine (MySQL).
    pub fn with_engine(mut self, engine: &str) -> Self {
        self.model.engine = Some(engine.to_string());
        self
    }
    
    /// Set the character set (MySQL).
    pub fn with_charset(mut self, charset: &str) -> Self {
        self.model.charset = Some(charset.to_string());
        self
    }
    
    /// Build the final model descriptor.
    pub fn build(self) -> ModelDescriptor {
        self.model
    }
    
    /// Build and validate the model descriptor.
    pub fn build_validated(self) -> Result<ModelDescriptor> {
        let model = self.model;
        validate_model(&model)?;
        Ok(model)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_validate_model_success() {
        let model = create_simple_model("users", None)
            .add_varchar_column("username", 100, false, true)
            .add_varchar_column("email", 255, false, true)
            .add_timestamps()
            .build();
        
        assert!(validate_model(&model).is_ok());
    }
    
    #[test]
    fn test_validate_model_empty_table_name() {
        let model = ModelDescriptor {
            name: "".to_string(),
            schema: None,
            columns: vec![],
            primary_key: None,
            indexes: vec![],
            constraints: vec![],
            comment: None,
            engine: None,
            charset: None,
            collation: None,
            options: Default::default(),
        };
        
        assert!(validate_model(&model).is_err());
    }
    
    #[test]
    fn test_validate_model_no_columns() {
        let model = ModelDescriptor {
            name: "test".to_string(),
            schema: None,
            columns: vec![],
            primary_key: None,
            indexes: vec![],
            constraints: vec![],
            comment: None,
            engine: None,
            charset: None,
            collation: None,
            options: Default::default(),
        };
        
        assert!(validate_model(&model).is_err());
    }
    
    #[test]
    fn test_validate_model_duplicate_columns() {
        let model = ModelDescriptor {
            name: "test".to_string(),
            schema: None,
            columns: vec![
                ColumnDescriptor {
                    name: "id".to_string(),
                    data_type: DataType::Integer(IntegerSize::I64),
                    is_nullable: false,
                    is_primary_key: true,
                    is_unique: false,
                    default_value: None,
                    auto_increment: true,
                    comment: None,
                    constraints: Vec::new(),
                },
                ColumnDescriptor {
                    name: "id".to_string(), // Duplicate name
                    data_type: DataType::Text(None),
                    is_nullable: true,
                    is_primary_key: false,
                    is_unique: false,
                    default_value: None,
                    auto_increment: false,
                    comment: None,
                    constraints: Vec::new(),
                },
            ],
            primary_key: None,
            indexes: vec![],
            constraints: vec![],
            comment: None,
            engine: None,
            charset: None,
            collation: None,
            options: Default::default(),
        };
        
        assert!(validate_model(&model).is_err());
    }
    
    #[test]
    fn test_model_builder_basic() {
        let model = ModelBuilder::new("test_table", Some("public"))
            .add_id_column()
            .add_varchar_column("name", 255, false, false)
            .add_boolean_column("active", false, Some(true))
            .add_timestamps()
            .with_comment("Test table")
            .build();
        
        assert_eq!(model.name, "test_table");
        assert_eq!(model.schema, Some("public".to_string()));
        assert_eq!(model.columns.len(), 5); // id, name, active, created_at, updated_at
        assert_eq!(model.comment, Some("Test table".to_string()));
        
        // Verify ID column
        let id_col = &model.columns[0];
        assert_eq!(id_col.name, "id");
        assert!(id_col.is_primary_key);
        assert!(id_col.auto_increment);
        assert!(!id_col.is_nullable);
        
        // Verify name column
        let name_col = &model.columns[1];
        assert_eq!(name_col.name, "name");
        assert!(!name_col.is_nullable);
        assert!(!name_col.is_unique);
        
        // Verify active column
        let active_col = &model.columns[2];
        assert_eq!(active_col.name, "active");
        assert!(!active_col.is_nullable);
        assert_eq!(active_col.default_value, Some("true".to_string()));
    }
    
    #[test]
    fn test_model_builder_with_constraints() {
        let model = ModelBuilder::new("posts", None)
            .add_id_column()
            .add_varchar_column("title", 255, false, false)
            .add_integer_column("user_id", IntegerSize::I64, false, false)
            .add_foreign_key(
                vec!["user_id".to_string()],
                "users",
                vec!["id".to_string()],
                Some(ReferentialAction::Cascade),
                Some(ReferentialAction::Restrict),
            )
            .add_index(vec!["title".to_string()], false)
            .add_unique_constraint(vec!["title".to_string(), "user_id".to_string()])
            .build();
        
        assert_eq!(model.constraints.len(), 2); // FK + unique constraint
        assert_eq!(model.indexes.len(), 1);
        
        // Verify foreign key constraint
        if let Constraint::ForeignKey { references_table, on_delete, on_update, .. } = &model.constraints[0] {
            assert_eq!(references_table, "users");
            assert_eq!(*on_delete, Some(ReferentialAction::Cascade));
            assert_eq!(*on_update, Some(ReferentialAction::Restrict));
        } else {
            panic!("Expected foreign key constraint");
        }
        
        // Verify unique constraint
        if let Constraint::Unique { columns, .. } = &model.constraints[1] {
            assert_eq!(columns.len(), 2);
            assert!(columns.contains(&"title".to_string()));
            assert!(columns.contains(&"user_id".to_string()));
        } else {
            panic!("Expected unique constraint");
        }
    }
    
    #[test]
    fn test_model_builder_validated() {
        // Valid model should succeed
        let result = ModelBuilder::new("valid_table", None)
            .add_id_column()
            .add_varchar_column("name", 100, false, false)
            .build_validated();
        
        assert!(result.is_ok());
        
        // Invalid model should fail
        let result = ModelBuilder::new("", None) // Empty table name
            .build_validated();
        
        assert!(result.is_err());
    }
    
    #[cfg(feature = "database")]
    #[test]
    fn test_get_adapter_for_database_type() {
        use crate::data::database::DatabaseType;
        
        let sqlite_adapter = get_adapter_for_database_type(DatabaseType::Sqlite);
        assert_eq!(sqlite_adapter.get_db_type_name(), "sqlite");
        
        let postgres_adapter = get_adapter_for_database_type(DatabaseType::Postgres);
        assert_eq!(postgres_adapter.get_db_type_name(), "postgres");
        
        let mysql_adapter = get_adapter_for_database_type(DatabaseType::MySql);
        assert_eq!(mysql_adapter.get_db_type_name(), "mysql");
    }
    
    #[cfg(feature = "database")]
    #[test]
    fn test_create_generator_for_database() {
        use crate::data::database::DatabaseType;
        
        let generator = create_generator_for_database(DatabaseType::Sqlite);
        assert_eq!(generator.adapter().get_db_type_name(), "sqlite");
    }
    
    #[cfg(feature = "database")]
    #[test]
    fn test_generate_complete_sql() {
        use crate::data::database::DatabaseType;
        
        let model = create_simple_model("test_users", None)
            .add_varchar_column("username", 100, false, true)
            .add_varchar_column("email", 255, false, true)
            .add_timestamps()
            .build();
        
        let sql = generate_complete_sql(&model, DatabaseType::Sqlite).unwrap();
        
        // Should contain CREATE TABLE statement
        assert!(sql.contains("CREATE TABLE"));
        assert!(sql.contains("test_users"));
        assert!(sql.contains("username"));
        assert!(sql.contains("email"));
        assert!(sql.contains("created_at"));
        assert!(sql.contains("updated_at"));
    }
    
    #[test]
    fn test_enum_column() {
        let model = ModelBuilder::new("products", None)
            .add_id_column()
            .add_enum_column(
                "status",
                "product_status",
                vec!["active".to_string(), "inactive".to_string(), "discontinued".to_string()],
                false,
            )
            .build();
        
        let status_col = &model.columns[1];
        assert_eq!(status_col.name, "status");
        if let DataType::Enum(enum_name, variants) = &status_col.data_type {
            assert_eq!(enum_name, "product_status");
            assert_eq!(variants.len(), 3);
            assert!(variants.contains(&"active".to_string()));
            assert!(variants.contains(&"inactive".to_string()));
            assert!(variants.contains(&"discontinued".to_string()));
        } else {
            panic!("Expected enum data type");
        }
    }
}