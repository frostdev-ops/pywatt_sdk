"""Template management for PyWatt CLI

This module provides templates for generating PyWatt module projects.
"""

from typing import Dict

# Available templates and their descriptions
AVAILABLE_TEMPLATES = {
    'pyproject.toml.j2': 'Python project configuration',
    'README.md.j2': 'Project documentation',
    'gitignore.j2': 'Git ignore file',
    'main_fastapi.py.j2': 'FastAPI main module',
    'main_flask.py.j2': 'Flask main module',
    'main_starlette.py.j2': 'Starlette main module',
    'main_none.py.j2': 'Basic main module',
    'requirements.txt.j2': 'Python dependencies',
    'Dockerfile.j2': 'Docker configuration',
    'docker-compose.yml.j2': 'Docker Compose configuration',
    'tests_init.py.j2': 'Test package initialization',
    'test_main.py.j2': 'Main test file',
    'conftest.py.j2': 'Pytest configuration',
    'github_ci.yml.j2': 'GitHub Actions CI/CD',
}

# Template contents
TEMPLATES = {
    'pyproject.toml.j2': '''[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{{ module_name }}"
dynamic = ["version"]
description = "PyWatt module: {{ module_name }}"
readme = "README.md"
license = "MIT"
requires-python = ">=3.8"
authors = [
    { name = "Your Name", email = "your.email@example.com" },
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
dependencies = [
    "pywatt_sdk>=0.3.0",
{% if use_fastapi %}
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
{% elif use_flask %}
    "flask>=3.0.0",
    "gunicorn>=21.2.0",
{% elif use_starlette %}
    "starlette>=0.27.0",
    "uvicorn[standard]>=0.24.0",
{% endif %}
{% if enable_database %}
{% if database == 'postgresql' %}
    "asyncpg>=0.29.0",
{% elif database == 'mysql' %}
    "aiomysql>=0.2.0",
{% elif database == 'sqlite' %}
    "aiosqlite>=0.19.0",
{% endif %}
{% endif %}
{% if enable_cache %}
{% if cache == 'redis' %}
    "redis>=5.0.0",
{% elif cache == 'memcached' %}
    "aiomcache>=0.7.0",
{% endif %}
{% endif %}
{% if enable_jwt %}
    "pyjwt[crypto]>=2.8.0",
{% endif %}
{% if enable_streaming %}
    "msgpack>=1.0.7",
{% endif %}
{% if enable_metrics %}
    "prometheus-client>=0.19.0",
{% endif %}
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-mock>=3.12.0",
    "black>=23.0.0",
    "isort>=5.12.0",
    "mypy>=1.7.0",
    "ruff>=0.1.0",
]

[project.urls]
Homepage = "https://github.com/yourusername/{{ module_name }}"
Repository = "https://github.com/yourusername/{{ module_name }}"
Issues = "https://github.com/yourusername/{{ module_name }}/issues"

[tool.hatch.version]
path = "{{ python_name }}/__init__.py"

[tool.black]
line-length = 100
target-version = ["py38"]

[tool.isort]
profile = "black"
line_length = 100

[tool.mypy]
python_version = "3.8"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.ruff]
line-length = 100
target-version = "py38"
''',

    'README.md.j2': '''# {{ module_name }}

A PyWatt module built with Python.

## Description

{{ module_name }} is a PyWatt module that provides [describe your module's functionality here].

## Features

- ✅ Built with PyWatt SDK {{ framework.upper() if framework != 'none' else 'Python' }}
{% if enable_database %}
- ✅ Database integration ({{ database.upper() if database else 'Multiple backends' }})
{% endif %}
{% if enable_cache %}
- ✅ Caching support ({{ cache.upper() if cache else 'Multiple backends' }})
{% endif %}
{% if enable_jwt %}
- ✅ JWT authentication
{% endif %}
{% if enable_streaming %}
- ✅ Streaming support
{% endif %}
{% if enable_metrics %}
- ✅ Prometheus metrics
{% endif %}
- ✅ Production-ready configuration
- ✅ Comprehensive testing
- ✅ Docker support

## Installation

```bash
pip install -e .
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black .
isort .

# Type checking
mypy .

# Linting
ruff check .
```

## Usage

```bash
python main.py
```

## Configuration

Set the following environment variables:

- `PYWATT_LOG_LEVEL`: Log level (default: INFO)
{% if enable_database %}
- `DATABASE_URL`: Database connection string
{% endif %}
{% if enable_cache %}
- `CACHE_URL`: Cache connection string
{% endif %}
{% if enable_jwt %}
- `JWT_SECRET`: JWT signing secret
{% endif %}

## Docker

```bash
# Build image
docker build -t {{ module_name }} .

# Run with docker-compose
docker-compose up
```

## License

MIT License - see LICENSE file for details.
''',

    'gitignore.j2': '''# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/
cover/

# Translations
*.mo
*.pot

# Django stuff:
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal

# Flask stuff:
instance/
.webassets-cache

# Scrapy stuff:
.scrapy

# Sphinx documentation
docs/_build/

# PyBuilder
.pybuilder/
target/

# Jupyter Notebook
.ipynb_checkpoints

# IPython
profile_default/
ipython_config.py

# pyenv
.python-version

# pipenv
Pipfile.lock

# poetry
poetry.lock

# pdm
.pdm.toml

# PEP 582
__pypackages__/

# Celery stuff
celerybeat-schedule
celerybeat.pid

# SageMath parsed files
*.sage.py

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre type checker
.pyre/

# pytype static type analyzer
.pytype/

# Cython debug symbols
cython_debug/

# PyCharm
.idea/

# VS Code
.vscode/

# macOS
.DS_Store

# Windows
Thumbs.db
ehthumbs.db
Desktop.ini
''',

    'main_fastapi.py.j2': '''"""{{ module_name }} - PyWatt module with FastAPI"""

import asyncio
from typing import Dict, Any

from fastapi import FastAPI, Depends
from pywatt_sdk import pywatt_module, AppState, AnnouncedEndpoint
{% if enable_database %}
from pywatt_sdk.data import DatabaseType
{% endif %}
{% if enable_cache %}
from pywatt_sdk.data import CacheType
{% endif %}


class {{ class_name }}State:
    """Custom application state for {{ module_name }}."""
    
    def __init__(self):
        self.initialized = False
        # Add your custom state here
    
    async def initialize(self) -> None:
        """Initialize the application state."""
        # Add your initialization logic here
        self.initialized = True


@pywatt_module(
    secrets=["DATABASE_URL", "JWT_SECRET"] if {{ enable_database or enable_jwt }} else [],
    rotate=True,
    endpoints=[
        AnnouncedEndpoint(path="/health", methods=["GET"], auth=None),
        AnnouncedEndpoint(path="/api/data", methods=["GET", "POST"], auth="jwt" if {{ enable_jwt }} else None),
    ],
    health="/health",
    metrics={{ enable_metrics | lower }},
    version="v1",
    state_builder=lambda init_data, secrets: {{ class_name }}State(),
    # Phase 3 features
{% if enable_database %}
    enable_database=True,
    database_config={
        "type": DatabaseType.{{ database.upper() if database else 'POSTGRESQL' }},
        "host": "localhost",
        "database": "{{ python_name }}",
    },
{% endif %}
{% if enable_cache %}
    enable_cache=True,
    cache_config={
        "type": CacheType.{{ cache.upper() if cache else 'REDIS' }},
        "host": "localhost",
        "port": {{ '6379' if cache == 'redis' else '11211' }},
    },
{% endif %}
{% if enable_jwt %}
    enable_jwt=True,
    jwt_config={
        "secret_key": "your-secret-key",
        "algorithm": "HS256",
    },
{% endif %}
{% if enable_streaming %}
    enable_streaming=True,
{% endif %}
{% if enable_metrics %}
    enable_metrics=True,
{% endif %}
)
async def create_app(state: AppState[{{ class_name }}State]) -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="{{ module_name }}",
        description="PyWatt module: {{ module_name }}",
        version="1.0.0",
    )
    
    # Initialize custom state
    await state.user_state.initialize()
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "module": "{{ module_name }}"}
    
    @app.get("/api/data")
    async def get_data(app_state: AppState[{{ class_name }}State] = Depends(lambda: state)):
        """Get data endpoint."""
{% if enable_database %}
        # Example database query
        # data = await app_state.execute_query("SELECT * FROM users LIMIT 10")
{% endif %}
{% if enable_cache %}
        # Example cache operation
        # cached_data = await app_state.cache_get("data_key")
        # if not cached_data:
        #     cached_data = {"example": "data"}
        #     await app_state.cache_set("data_key", cached_data, ttl=3600)
{% endif %}
        
        return {
            "message": "Hello from {{ module_name }}!",
            "initialized": app_state.user_state.initialized,
        }
    
    @app.post("/api/data")
    async def create_data(
        data: Dict[str, Any],
        app_state: AppState[{{ class_name }}State] = Depends(lambda: state)
    ):
        """Create data endpoint."""
        # Add your data creation logic here
        return {"message": "Data created", "data": data}
    
    return app


if __name__ == "__main__":
    # This will be handled by the @pywatt_module decorator
    pass
''',

    'main_flask.py.j2': '''"""{{ module_name }} - PyWatt module with Flask"""

from typing import Dict, Any

from flask import Flask, request, jsonify
from pywatt_sdk import pywatt_module, AppState, AnnouncedEndpoint


class {{ class_name }}State:
    """Custom application state for {{ module_name }}."""
    
    def __init__(self):
        self.initialized = False
        # Add your custom state here
    
    async def initialize(self) -> None:
        """Initialize the application state."""
        # Add your initialization logic here
        self.initialized = True


@pywatt_module(
    secrets=["DATABASE_URL", "JWT_SECRET"] if {{ enable_database or enable_jwt }} else [],
    rotate=True,
    endpoints=[
        AnnouncedEndpoint(path="/health", methods=["GET"], auth=None),
        AnnouncedEndpoint(path="/api/data", methods=["GET", "POST"], auth="jwt" if {{ enable_jwt }} else None),
    ],
    health="/health",
    metrics={{ enable_metrics | lower }},
    version="v1",
    state_builder=lambda init_data, secrets: {{ class_name }}State(),
)
async def create_app(state: AppState[{{ class_name }}State]) -> Flask:
    """Create and configure the Flask application."""
    
    app = Flask(__name__)
    
    # Initialize custom state
    await state.user_state.initialize()
    
    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint."""
        return jsonify({"status": "healthy", "module": "{{ module_name }}"})
    
    @app.route("/api/data", methods=["GET"])
    def get_data():
        """Get data endpoint."""
        return jsonify({
            "message": "Hello from {{ module_name }}!",
            "initialized": state.user_state.initialized,
        })
    
    @app.route("/api/data", methods=["POST"])
    def create_data():
        """Create data endpoint."""
        data = request.get_json()
        # Add your data creation logic here
        return jsonify({"message": "Data created", "data": data})
    
    return app


if __name__ == "__main__":
    # This will be handled by the @pywatt_module decorator
    pass
''',

    'main_none.py.j2': '''"""{{ module_name }} - Basic PyWatt module"""

import asyncio
from pywatt_sdk import pywatt_module, AppState, AnnouncedEndpoint


class {{ class_name }}State:
    """Custom application state for {{ module_name }}."""
    
    def __init__(self):
        self.initialized = False
        # Add your custom state here
    
    async def initialize(self) -> None:
        """Initialize the application state."""
        # Add your initialization logic here
        self.initialized = True


@pywatt_module(
    secrets=[] if not {{ enable_database or enable_jwt }} else ["DATABASE_URL", "JWT_SECRET"],
    rotate=True,
    endpoints=[],
    state_builder=lambda init_data, secrets: {{ class_name }}State(),
)
async def main(state: AppState[{{ class_name }}State]) -> None:
    """Main module function."""
    
    # Initialize custom state
    await state.user_state.initialize()
    
    print(f"{{ module_name }} started successfully!")
    print(f"Module ID: {state.module_id}")
    print(f"Initialized: {state.user_state.initialized}")
    
    # Your main logic here
    try:
        while True:
            # Example: process messages, handle events, etc.
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("Shutting down {{ module_name }}...")


if __name__ == "__main__":
    # This will be handled by the @pywatt_module decorator
    pass
''',
}


def get_template_content(template_name: str) -> str:
    """Get the content of a template by name."""
    if template_name not in TEMPLATES:
        raise ValueError(f"Template '{template_name}' not found")
    return TEMPLATES[template_name] 