---
trigger: model_decision
description: This rule documents patterns and best practices for handling multipart form data in the PyWatt-Rust project.
globs: 
---
# Multipart Form Data

<context>
This rule documents patterns and best practices for handling multipart form data in the PyWatt-Rust project.
</context>

<rules>

## Type Safety
- Always convert text fields to `String` instead of using `str`
- Always convert binary fields to owned `Vec<u8>` instead of using `[u8]`
- Use explicit typing and avoid using unsized types for local variables

## Field Extraction
- Use `field.text().await?.to_string()` for text fields
- Use `field.bytes().await?.to_vec()` for binary fields
- Always handle potential errors with `?` or explicit error handling
- Use `Option<String>` and `Option<Vec<u8>>` for optional fields

## File Handling
- Validate file sizes before processing
- Check file types before processing (using content type or magic bytes)
- Store files in a dedicated storage system rather than in the database
- Use appropriate content dispositions for downloaded files

## Error Handling
- Provide clear error messages for invalid forms
- Return 400 Bad Request for invalid form data
- Handle missing required fields explicitly
- Validate field content before processing

</rules>

<patterns>

## Text Field Extraction
```rust
// Extract a text field from a multipart form
let name = if let Some(field) = form.next().await {
    let field = field?;
    if field.name() == "name" {
        Some(field.text().await?.to_string())
    } else {
        None
    }
} else {
    None
};

// Use the field with proper null checking
let name = name.ok_or_else(|| AppError::BadRequest("Name field is required".to_string()))?;
```

## Binary Field Extraction
```rust
// Extract a binary field from a multipart form
let file_data = if let Some(field) = form.next().await {
    let field = field?;
    if field.name() == "file" {
        Some(field.bytes().await?.to_vec())
    } else {
        None
    }
} else {
    None
};

// Use the field with proper null checking
let file_data = file_data.ok_or_else(|| AppError::BadRequest("File data is required".to_string()))?;
```

## Field Metadata Extraction
```rust
// Extract file metadata
let content_type = field.content_type().map(|ct| ct.to_string());
let filename = field.file_name().map(|name| name.to_string());
```

</patterns>

<examples>

## Complete Form Handling
```rust
/// Upload a document
async fn upload_document(
    State(state): State<AppState>,
    auth_user: AuthUser,
    mut multipart: Multipart,
) -> AppResult<impl IntoResponse> {
    // Prepare variables to collect form data
    let mut name: Option<String> = None;
    let mut description: Option<String> = None;
    let mut file_data: Option<Vec<u8>> = None;
    let mut metadata: Option<serde_json::Value> = None;
    
    // Process each field in the form
    while let Some(field) = multipart.next_field().await? {
        let field_name = field.name().unwrap_or_default();
        
        match field_name {
            "name" => {
                name = Some(field.text().await?.to_string());
            },
            "description" => {
                description = Some(field.text().await?.to_string());
            },
            "file" => {
                // Get binary data
                file_data = Some(field.bytes().await?.to_vec());
            },
            "metadata" => {
                let metadata_str = field.text().await?.to_string();
                metadata = Some(serde_json::from_str(&metadata_str)?);
            },
            _ => {
                // Ignore unknown fields
            }
        }
    }
    
    // Validate required fields
    let name = name.ok_or_else(|| AppError::BadRequest("Document name is required".to_string()))?;
    let file_data = file_data.ok_or_else(|| AppError::BadRequest("File data is required".to_string()))?;
    
    // Process the upload
    let document = state.document_service.upload_document(
        auth_user.user_id,
        name,
        description,
        file_data,
        metadata,
    ).await?;
    
    Ok((StatusCode::CREATED, Json(document)))
}
```

## Streaming Large Files
```rust
/// Stream a file from a multipart form to storage
async fn handle_large_file(
    mut field: axum::extract::multipart::Field<'_>,
    storage: &StorageService,
) -> AppResult<String> {
    let filename = field.file_name()
        .map(|name| name.to_string())
        .ok_or_else(|| AppError::BadRequest("Filename is required".to_string()))?;
    
    let content_type = field.content_type()
        .map(|ct| ct.to_string())
        .unwrap_or_else(|| "application/octet-stream".to_string());
    
    // Create a unique ID for the file
    let file_id = Uuid::new_v4().to_string();
    
    // Create a temporary file on disk
    let temp_path = format!("/tmp/{}", file_id);
    let mut file = tokio::fs::File::create(&temp_path).await?;
    
    // Stream the data to the file
    while let Some(chunk) = field.chunk().await? {
        file.write_all(&chunk).await?;
    }
    
    // Close the file
    file.flush().await?;
    
    // Upload the file to permanent storage
    let url = storage.upload_file(&temp_path, &filename, &content_type).await?;
    
    // Clean up the temporary file
    tokio::fs::remove_file(&temp_path).await?;
    
    Ok(url)
}
```

</examples>

<troubleshooting>

## Common Errors
- "the size for values of type `str` cannot be known at compilation time"
  - Cause: Using `str` directly as a variable type
  - Fix: Use `String` instead, e.g., `field.text().await?.to_string()`

- "the size for values of type `[u8]` cannot be known at compilation time"
  - Cause: Using `[u8]` directly as a variable type
  - Fix: Use `Vec<u8>` instead, e.g., `field.bytes().await?.to_vec()`

- "field of struct `X` does not implement `std::marker::Send`"
  - Cause: Using synchronous I/O in async context
  - Fix: Use async file I/O operations with tokio

## Field Extraction Issues
- If you can't determine field order, use field names to identify them
- If a field might appear multiple times, collect them into a vector
- When expecting JSON data, validate it using `serde_json::from_str`
- For large file uploads, stream to disk rather than loading entirely into memory

## Performance Considerations
- Set appropriate size limits for uploads
- Consider streaming large files directly to storage rather than loading into memory
- Use connection pooling for database operations during uploads
- Implement rate limiting for file uploads

</troubleshooting>
