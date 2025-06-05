#!/usr/bin/env python3
"""Example demonstrating the PyWatt Model Manager functionality.

This example shows how to:
1. Define database models using the builder pattern
2. Generate SQL for different database types
3. Apply models to a database
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import Model Manager components
from services.model_manager import (
    ModelBuilder,
    ModelDescriptor,
    DataType,
    IntegerSize,
    ReferentialAction,
    create_simple_model,
    validate_model,
    generate_complete_sql,
    ModelManager,
    ModelManagerConfig,
    ColumnDescriptor,
)
from data.database import DatabaseType


def create_user_model() -> ModelDescriptor:
    """Create a user model using the builder pattern."""
    return (
        create_simple_model("users")
        .add_varchar_column("username", 100, nullable=False, unique=True)
        .add_varchar_column("email", 255, nullable=False, unique=True)
        .add_varchar_column("password_hash", 255, nullable=False)
        .add_varchar_column("full_name", 200, nullable=True)
        .add_boolean_column("is_active", nullable=False, default=True)
        .add_boolean_column("is_admin", nullable=False, default=False)
        .add_timestamps()
        .add_index(["email"], unique=True, name="idx_users_email")
        .add_index(["username"], unique=True, name="idx_users_username")
        .with_comment("User accounts table")
        .build()
    )


def create_post_model() -> ModelDescriptor:
    """Create a blog post model with foreign key to users."""
    return (
        ModelBuilder("posts")
        .add_id_column()
        .add_varchar_column("title", 200, nullable=False)
        .add_text_column("content", nullable=False)
        .add_integer_column("author_id", IntegerSize.I64, nullable=False)
        .add_enum_column(
            "status",
            "post_status",
            ["draft", "published", "archived"],
            nullable=False,
            default="draft"
        )
        .add_integer_column("view_count", IntegerSize.I32, nullable=False, default=0)
        .add_json_column("metadata", nullable=True, binary=True)  # JSONB for PostgreSQL
        .add_timestamps()
        .add_foreign_key(
            ["author_id"],
            "users",
            ["id"],
            on_delete=ReferentialAction.CASCADE,
            name="fk_posts_author"
        )
        .add_index(["author_id"], name="idx_posts_author")
        .add_index(["status", "created_at"], name="idx_posts_status_date")
        .with_comment("Blog posts table")
        .build()
    )


def create_comment_model() -> ModelDescriptor:
    """Create a comment model with foreign keys to posts and users."""
    return (
        ModelBuilder("comments")
        .add_id_column()
        .add_integer_column("post_id", IntegerSize.I64, nullable=False)
        .add_integer_column("user_id", IntegerSize.I64, nullable=False)
        .add_text_column("content", nullable=False)
        .add_boolean_column("is_approved", nullable=False, default=False)
        .add_timestamps()
        .add_foreign_key(
            ["post_id"],
            "posts",
            ["id"],
            on_delete=ReferentialAction.CASCADE,
            name="fk_comments_post"
        )
        .add_foreign_key(
            ["user_id"],
            "users",
            ["id"],
            on_delete=ReferentialAction.CASCADE,
            name="fk_comments_user"
        )
        .add_index(["post_id", "created_at"], name="idx_comments_post_date")
        .add_check_constraint("LENGTH(content) > 0", name="chk_comments_not_empty")
        .with_comment("Comments on blog posts")
        .build()
    )


def demonstrate_sql_generation():
    """Demonstrate SQL generation for different database types."""
    print("=== Model Manager SQL Generation Demo ===\n")
    
    # Create models
    models = [
        create_user_model(),
        create_post_model(),
        create_comment_model(),
    ]
    
    # Validate models
    print("1. Validating models...")
    for model in models:
        try:
            validate_model(model)
            print(f"   ✓ Model '{model.name}' is valid")
        except Exception as e:
            print(f"   ✗ Model '{model.name}' validation failed: {e}")
    
    print("\n2. Generating SQL for different databases:\n")
    
    # Generate SQL for each database type
    for db_type in [DatabaseType.SQLITE, DatabaseType.POSTGRESQL, DatabaseType.MYSQL]:
        print(f"\n--- {db_type.value.upper()} SQL ---")
        
        for model in models:
            try:
                sql = generate_complete_sql(model, db_type)
                print(f"\n-- Table: {model.name}")
                print(sql)
            except Exception as e:
                print(f"Error generating SQL for {model.name}: {e}")


async def demonstrate_model_application():
    """Demonstrate applying models to a database (mock example)."""
    print("\n\n=== Model Manager Database Application Demo ===\n")
    
    # Create models
    models = [
        create_user_model(),
        create_post_model(),
        create_comment_model(),
    ]
    
    # Mock database connection
    class MockDatabaseConnection:
        """Mock database connection for demonstration."""
        
        async def execute(self, sql: str) -> None:
            print(f"EXECUTE: {sql}")
    
    # Create model manager configuration
    config = ModelManagerConfig(
        database_connection=MockDatabaseConnection(),
        database_type=DatabaseType.POSTGRESQL,
        auto_create_schemas=True,
        dry_run=False,  # Set to True to only generate SQL without executing
    )
    
    # Create model manager
    manager = ModelManager(config, models)
    
    # Apply models
    print("Applying models to database...")
    statements = await manager.apply_models()
    
    print(f"\nExecuted {len(statements)} SQL statements")
    print(f"Applied models: {manager.get_applied_models()}")
    
    # Generate migration script
    print("\n\n--- Complete Migration Script ---")
    migration_script = manager.generate_migration_script()
    print(migration_script)


def demonstrate_model_builder_features():
    """Demonstrate advanced model builder features."""
    print("\n\n=== Advanced Model Builder Features ===\n")
    
    # Create a complex model with various column types
    model = (
        ModelBuilder("products", schema_name="shop")
        .add_id_column()
        .add_varchar_column("sku", 50, nullable=False, unique=True)
        .add_varchar_column("name", 200, nullable=False)
        .add_text_column("description")
        .add_decimal_column("price", 10, 2, nullable=False)
        .add_integer_column("stock_quantity", IntegerSize.I32, nullable=False, default=0)
        .add_boolean_column("is_available", nullable=False, default=True)
        .add_uuid_column("external_id", unique=True, default="gen_random_uuid()")
        .add_json_column("attributes", binary=True)
        .add_enum_column(
            "category",
            "product_category",
            ["electronics", "clothing", "food", "books", "other"],
            nullable=False,
            default="other"
        )
        .add_timestamps()
        .add_index(["category", "is_available"], name="idx_products_category_available")
        .add_index(["price"], name="idx_products_price")
        .add_check_constraint("price > 0", name="chk_products_positive_price")
        .add_check_constraint("stock_quantity >= 0", name="chk_products_non_negative_stock")
        .with_comment("Product catalog")
        .with_engine("InnoDB")  # MySQL specific
        .with_charset("utf8mb4")  # MySQL specific
        .with_collation("utf8mb4_unicode_ci")  # MySQL specific
        .build_validated()  # Build and validate in one step
    )
    
    print("Created complex product model:")
    print(f"- Table: {model.name}")
    print(f"- Schema: {model.schema}")
    print(f"- Columns: {len(model.columns)}")
    print(f"- Indexes: {len(model.indexes)}")
    print(f"- Constraints: {len(model.constraints)}")
    
    # Generate SQL for PostgreSQL
    sql = generate_complete_sql(model, DatabaseType.POSTGRESQL)
    print("\nGenerated PostgreSQL SQL:")
    print(sql)


def demonstrate_decimal_column():
    """Demonstrate adding decimal columns."""
    print("\n\n=== Decimal Column Example ===\n")
    
    # Add helper method to ModelBuilder for decimal columns
    def add_decimal_column(
        self,
        name: str,
        precision: int,
        scale: int,
        nullable: bool = True,
        default: Optional[float] = None,
        comment: Optional[str] = None,
    ) -> "ModelBuilder":
        """Add a decimal column."""
        self.model.columns.append(ColumnDescriptor(
            name=name,
            data_type=DataType.decimal(precision, scale),
            is_nullable=nullable,
            is_primary_key=False,
            is_unique=False,
            default_value=str(default) if default is not None else None,
            auto_increment=False,
            comment=comment,
            constraints=[],
        ))
        return self
    
    # Monkey patch the method for this example
    ModelBuilder.add_decimal_column = add_decimal_column
    
    # Now use it
    model = (
        create_simple_model("orders")
        .add_decimal_column("subtotal", 10, 2, nullable=False, default=0.00)
        .add_decimal_column("tax", 10, 2, nullable=False, default=0.00)
        .add_decimal_column("total", 10, 2, nullable=False, default=0.00)
        .build()
    )
    
    sql = generate_complete_sql(model, DatabaseType.MYSQL)
    print("Order model with decimal columns (MySQL):")
    print(sql)


def main():
    """Run all demonstrations."""
    # SQL generation demo
    demonstrate_sql_generation()
    
    # Model builder features
    demonstrate_model_builder_features()
    
    # Decimal column example
    demonstrate_decimal_column()
    
    # Database application demo (async)
    asyncio.run(demonstrate_model_application())


if __name__ == "__main__":
    main() 