"""Simple PyWatt module example.

This example demonstrates how to create a basic PyWatt module using the
@pywatt_module decorator with secret management and endpoint announcement.
"""

import asyncio
from typing import Dict, Any

from pywatt_sdk import (
    pywatt_module,
    AppState,
    AnnouncedEndpoint,
    info,
)


# Define custom state for our module
class MyModuleState:
    """Custom state for our module."""
    
    def __init__(self, api_key: str, database_url: str):
        self.api_key = api_key
        self.database_url = database_url
        self.request_count = 0
    
    def increment_requests(self) -> int:
        """Increment and return request count."""
        self.request_count += 1
        return self.request_count


def build_state(init_data, secrets) -> MyModuleState:
    """Build custom state from initialization data and secrets.
    
    Args:
        init_data: Initialization data from orchestrator
        secrets: List of fetched secrets
        
    Returns:
        Custom module state
    """
    # Extract secrets (they're in the same order as requested)
    api_key = secrets[0].expose_secret() if len(secrets) > 0 else "default-key"
    database_url = secrets[1].expose_secret() if len(secrets) > 1 else "sqlite:///default.db"
    
    return MyModuleState(api_key, database_url)


@pywatt_module(
    secrets=["API_KEY", "DATABASE_URL"],
    rotate=True,
    endpoints=[
        AnnouncedEndpoint(
            path="/api/data",
            methods=["GET", "POST"],
            auth="jwt"
        ),
        AnnouncedEndpoint(
            path="/api/status",
            methods=["GET"],
            auth=None
        ),
    ],
    health="/health",
    metrics=True,
    version="v1",
    state_builder=build_state
)
async def create_app(state: AppState[MyModuleState]) -> Dict[str, Any]:
    """Create the application.
    
    Args:
        state: Application state with custom user state
        
    Returns:
        Application object (in this case, a simple dict for demonstration)
    """
    info(f"Creating application for module {state.module_id}")
    info(f"Custom state API key: {state.user_state.api_key[:5]}...")
    
    # In a real application, this would return a FastAPI, Flask, or other web framework app
    # For this example, we'll return a simple dict representing our "app"
    app = {
        "type": "simple_module",
        "module_id": state.module_id,
        "endpoints": [
            "/health",
            "/metrics", 
            "/v1/api/data",
            "/v1/api/status"
        ],
        "state": state
    }
    
    return app


async def main():
    """Main entry point for the module."""
    try:
        # The @pywatt_module decorator handles all the initialization
        app, app_state, ipc_task = await create_app()
        
        info(f"Module initialized successfully: {app['type']}")
        info(f"Available endpoints: {app['endpoints']}")
        
        # In a real application, you would start your web server here
        # For this example, we'll just wait for the IPC task
        info("Module is running. Press Ctrl+C to stop.")
        
        # Keep the module running
        await ipc_task
        
    except KeyboardInterrupt:
        info("Module shutting down due to keyboard interrupt")
    except Exception as e:
        info(f"Module terminated with error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main()) 