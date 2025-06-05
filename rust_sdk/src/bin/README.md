# `pywatt_sdk/rust_sdk/src/bin`

This directory contains executable tools that are part of the PyWatt Rust SDK.

## `database_tool.rs`

`database_tool.rs` is a command-line interface (CLI) utility for managing database schemas and models. It is built using Rust and the `clap` crate for command-line argument parsing, and integrates with other components of the `pywatt_sdk`.

### Features

The tool provides two main categories of commands: `schema` and `model`.

#### Schema Commands (`schema`)

-   **`generate`**: 
    -   Generates SQL Data Definition Language (DDL) scripts from model definition files (supports YAML or JSON format).
    -   Can target different database systems: SQLite, MySQL, and PostgreSQL.
    -   Outputs the generated script to a specified file or to standard output.
-   **`apply`**:
    -   Applies a schema (derived from model definitions) to a target database.
    -   Requires a database configuration file (TOML format) to connect to the database.

#### Model Commands (`model`)

-   **`validate`**:
    -   Validates model definition files by attempting to generate the corresponding SQL (internally uses an SQLite adapter for this process).
-   **`generate`**:
    -   Generates Rust struct definitions based on the provided model definition files.
    -   Outputs the generated Rust code to a specified file or to standard output.
-   **`apply`**:
    -   Applies model definitions directly to a database, which can involve creating new tables or altering existing ones.
    -   Requires a model definition file and a database configuration file.
-   **`drop`**:
    -   Removes a specified table from the database.
    -   Requires the table name and a database configuration file. An optional schema name can also be provided.

### Usage

This tool is intended to be compiled into an executable. The specific commands and their arguments can be discovered by running the compiled executable with the `--help` flag.

For example (assuming the compiled binary is named `database-tool`):

```bash
./database-tool --help
./database-tool schema --help
./database-tool schema generate --help
./database-tool model --help
```
