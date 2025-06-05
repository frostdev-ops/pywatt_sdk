---
trigger: model_decision
description: This rule documents best practices for converting between String and &str types in the PyWatt-Rust project, including common patterns and functions for efficient and safe string handling.
globs: 
---
# Rust String Conversion

<context>
This rule documents best practices for converting between String and &str types in the PyWatt-Rust project, including common patterns and functions for efficient and safe string handling.
</context>

<rules>

## String to &str Conversion
- Use `&string` for temporary references to the entire string
- Use `string.as_str()` for explicit conversion to a string slice
- Use `string.as_deref()` when dealing with `Option<String>` to convert to `Option<&str>`
- Never force clone or copy strings unless needed for ownership

## &str to String Conversion
- Use `string.to_string()` for creating owned copies of string slices
- Use `String::from(str)` as an alternative to `to_string()`
- Use `format!("...{}", str)` when combining strings
- Use `str.to_owned()` for creating owned strings from slices

## Option Handling
- Always use `as_deref()` when converting `Option<String>` to `Option<&str>`
- Use `map(|s| s.as_str())` as an alternative when more complex mapping is needed
- For `Result<String, E>`, use `as_deref()` or `map(|s| s.as_str())` on the Ok variant

## Performance Considerations
- Prefer borrowing (`&str`) over owning (`String`) when possible
- Only clone strings when necessary for ownership or data structure requirements
- Use string slices for function parameters to accept both `String` and `&str`
- Return `String` from functions that create or modify strings, `&str` for views into existing data

</rules>

<patterns>

## Option<String> to Option<&str>
```rust
// Converting Option<String> to Option<&str>
fn process_optional_string(name: Option<&str>) -> Result<(), Error> {
    // Implementation
}

// Call site
let name: Option<String> = Some("John".to_string());
process_optional_string(name.as_deref())
```

## String Function Parameters
```rust
// Accept both String and &str by using &str parameters
fn process_name(name: &str) -> Result<(), Error> {
    // Implementation using name directly
}

// Call site examples
let owned_name = "John".to_string();
process_name(&owned_name);  // Works with String reference
process_name("John");       // Works with string literal
```

## Returning String or &str
```rust
// Return String when creating new data
fn generate_greeting(name: &str) -> String {
    format!("Hello, {}!", name)
}

// Return &str when providing a view into existing data
fn get_name<'a>(user: &'a User) -> &'a str {
    &user.name
}
```

## Working with String Collections
```rust
// Convert Vec<String> to Vec of string slices for processing
fn process_names(names: &[String]) -> Result<(), Error> {
    let name_slices: Vec<&str> = names.iter().map(|s| s.as_str()).collect();
    // Process name_slices
}

// Alternative using references
fn process_names_alt(names: &[String]) -> Result<(), Error> {
    for name in names {
        let name_str = name.as_str();
        // Process each name_str
    }
}
```

</patterns>

<examples>

## Complete Function Example with Option<String>
```rust
/// Update a customer's information
pub async fn update_customer(
    &self,
    id: Uuid,
    email: Option<&str>,
    name: Option<&str>,
    billing_address: Option<serde_json::Value>,
    shipping_address: Option<serde_json::Value>,
    payment_method_id: Option<&str>,
) -> AppResult<Customer> {
    // Database update implementation
}

// Call site
let updated_customer = customer_service
    .update_customer(
        id,
        request.email.as_deref(),        // Convert Option<String> to Option<&str>
        request.name.as_deref(),         // Convert Option<String> to Option<&str>
        request.billing_address,
        request.shipping_address,
        request.payment_method_id.as_deref(),  // Convert Option<String> to Option<&str>
    )
    .await?;
```

## String Handling in API Routes
```rust
/// Search for resources by name
async fn search_resources(
    Query(params): Query<SearchParams>,
) -> AppResult<Json<Vec<Resource>>> {
    let query = params.query.as_deref().unwrap_or("");
    let resources = db.search(query).await?;
    Ok(Json(resources))
}

#[derive(Deserialize)]
struct SearchParams {
    query: Option<String>,
    limit: Option<i64>,
}
```

## String Conversion in Data Processing
```rust
pub fn normalize_text(input: &str) -> String {
    // Create a new string with modifications
    input.trim()
        .to_lowercase()
        .replace("  ", " ")
}

pub fn extract_domain<'a>(email: &'a str) -> Option<&'a str> {
    // Return a slice of the input string
    email.split('@').nth(1)
}

pub fn process_input(input: Option<String>) -> Result<(), Error> {
    match input.as_deref() {
        Some("") | None => return Err(Error::EmptyInput),
        Some(text) => {
            // Process the text slice
            println!("Processing: {}", text);
        }
    }
    Ok(())
}
```

</examples>

<common_issues>

## Unnecessary Cloning
```rust
// Bad: Unnecessary clone
fn process(text: &str) {
    let owned = text.to_string();  // Unnecessary conversion to owned String
    // Use owned...
}

// Good: Use the reference directly
fn process(text: &str) {
    // Use text directly...
}
```

## Missing as_deref()
```rust
// Bad: Type mismatch
fn process(name: Option<&str>) -> Result<(), Error> {
    // Implementation
}

let name: Option<String> = Some("John".to_string());
process(name)  // Error: expected Option<&str>, found Option<String>

// Good: Use as_deref()
process(name.as_deref())
```

## Inefficient String Building
```rust
// Bad: Multiple allocations
let mut result = String::new();
result.push_str("Hello, ");
result.push_str(&name);
result.push_str("!");

// Good: Single allocation with format!
let result = format!("Hello, {}!", name);
```

## Incorrect Lifetime Management
```rust
// Bad: Returning reference to temporary value
fn get_greeting(name: &str) -> &str {
    format!("Hello, {}!", name).as_str()  // Error: returns reference to local data
}

// Good: Return owned String
fn get_greeting(name: &str) -> String {
    format!("Hello, {}!", name)
}
```

</common_issues>

<dependencies>

## Standard Library Types
- `String`: Owned, growable UTF-8 string type
- `&str`: Borrowed string slice type
- `Option<T>`: Type for optional values
- `Vec<T>`: Growable array type for collections

## Methods and Functions
- `as_str()`: Convert `String` to `&str`
- `as_deref()`: Convert `Option<String>` to `Option<&str>`
- `to_string()`: Convert `&str` to `String`
- `to_owned()`: Create owned data from borrowed data
- `String::from()`: Create `String` from `&str`
- `format!()`: Format string with interpolation

</dependencies>
