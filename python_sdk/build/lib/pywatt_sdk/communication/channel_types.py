"""Channel types and preferences.

This module re-exports channel types and preferences for backward compatibility.
"""

# Re-export from message_channel for backward compatibility
from .message_channel import (
    ChannelType,
    ConnectionState,
    ChannelCapabilities,
    ChannelPreferences,
    MessageChannel,
    ChannelManager,
    get_global_channel_manager,
    set_global_channel_manager,
)

__all__ = [
    "ChannelType",
    "ConnectionState", 
    "ChannelCapabilities",
    "ChannelPreferences",
    "MessageChannel",
    "ChannelManager",
    "get_global_channel_manager",
    "set_global_channel_manager",
] 