---
trigger: model_decision
description: This rule documents the ChatService in the PyWatt-Rust project, which is responsible for managing conversations, messages, and participants.
globs: 
---
# Chat Service

<context>
This rule documents the ChatService in the PyWatt-Rust project, which is responsible for managing conversations, messages, and participants.
</context>

<rules>

## Service Structure
- The `ChatService` handles all conversation-related operations
- It uses a PostgreSQL database connection pool for data access
- Core functionality includes:
  - Creating and managing conversations
  - Sending and retrieving messages
  - Managing participants and access control
  - Supporting attachment uploads

## Key Methods
- `new(db_pool)` - Creates a new ChatService instance
- `create_conversation(created_by, params)` - Creates a new conversation
- `send_message(params)` - Sends a message to a conversation
- `list_messages(conversation_id, user_id, limit, before)` - Lists messages in a conversation
- `get_conversation(conversation_id, user_id)` - Retrieves a conversation by ID
- `add_participant(conversation_id, user_id, added_by, role)` - Adds a participant to a conversation
- `remove_participant(conversation_id, user_id, removed_by)` - Removes a participant from a conversation
- `list_conversations(params)` - Lists conversations for a user
- `mark_read(conversation_id, user_id, message_id)` - Marks a conversation as read
- `is_participant(conversation_id, user_id)` - Checks if a user is a participant
- `get_participant_role(conversation_id, user_id)` - Gets a participant's role

## Access Control Pattern
- Every operation that accesses a conversation first checks if the user is a participant
- Use `is_participant(conversation_id, user_id)` for this check
- Role-based permissions are enforced for sensitive operations using `get_participant_role`

## Transaction Usage
- Some operations use transactions for data consistency
- Example: Creating a conversation with initial participants
- Always use the `&mut *tx` pattern when executing queries within a transaction

</rules>

<patterns>

## Participant Check
```rust
// Check if the user is a participant in the conversation
if !self.is_participant(conversation_id, user_id).await? {
    return Err(AppError::ForbiddenError(format!(
        "User {} is not a participant in conversation {}",
        user_id, conversation_id
    )));
}
```

## Send Message
```rust
// Example of sending a message
let params = SendMessageParams {
    conversation_id,
    user_id: Some(user_id),
    role: MessageRole::User,
    message_type: MessageType::Text,
    content: "Hello, world!".to_string(),
    content_parts: None,
    metadata: None,
};

let message = chat_service.send_message(params).await?;
```

## Role-Based Permission Check
```rust
// Get the user's role in the conversation
let user_role = self.get_participant_role(conversation_id, user_id).await?;

// Check if the user has permission to perform the operation
match user_role {
    ParticipantRole::Owner => {
        // Owner can do anything
    },
    ParticipantRole::Admin => {
        // Admin can do most things, but not remove an owner
    },
    _ => {
        // Regular participants have limited permissions
        return Err(AppError::ForbiddenError("Insufficient permissions".to_string()));
    }
}
```

</patterns>

<examples>

## Creating a Conversation
```rust
// Create a new conversation
let params = CreateConversationParams {
    title: "Team Chat".to_string(),
    description: Some("Team discussion".to_string()),
    conversation_type: ConversationType::Group,
    is_ai_enabled: true,
    participants: vec![user_id1, user_id2],
};

let conversation = chat_service.create_conversation(creator_id, params).await?;
```

## Adding a Participant
```rust
// Add a participant to a conversation
let participant = chat_service.add_participant(
    conversation_id, 
    new_user_id, 
    admin_user_id, 
    ParticipantRole::Member
).await?;
```

## Sending a System Message
```rust
// Send a system message
let params = SendMessageParams {
    conversation_id,
    user_id: None,  // System message has no user
    role: MessageRole::System,
    message_type: MessageType::Text,
    content: "User has joined the chat".to_string(),
    content_parts: None,
    metadata: Some(serde_json::json!({
        "event_type": "user_joined",
        "user_id": user_id.to_string()
    })),
};

let message = chat_service.send_message(params).await?;
```

## Checking Participant Access
```rust
// Check if a user has access to a conversation (for WebSocket)
async fn handle_join_conversation(
    chat_service: Arc<ChatService>,
    conversation_id: Uuid,
    user_id: Uuid,
) -> AppResult<()> {
    if !chat_service.is_participant(conversation_id, user_id).await? {
        return Err(AppError::ForbiddenError(
            "You don't have access to this conversation".to_string()
        ));
    }
    
    // Continue with join operation...
    Ok(())
}
```

</examples>

<troubleshooting>

## Common Errors
- "User is not a participant in conversation" - The user ID is not in the participants table
- "method `is_participant` not found" - Ensure you're using the correct method name and parameters
- "Expected &mut PgConnection, found &PgPool" - Use query methods on the pool directly, or begin a transaction

## Database Connection Issues
- When queries fail with connection errors, check:
  1. Is the database pool correctly initialized?
  2. Are you using the right pool instance?
  3. For transactions, are you using `&mut *tx` pattern correctly?

## Transaction Pattern
- Use `let mut tx = self.db_pool.begin().await?;` to start a transaction
- Execute queries with `&mut *tx` as the connection parameter
- Complete with `tx.commit().await?;` or `tx.rollback().await?;`

</troubleshooting>
