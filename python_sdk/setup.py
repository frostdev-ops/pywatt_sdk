#!/usr/bin/env python3
"""Setup script for PyWatt Python SDK."""

from setuptools import setup, find_packages
import os

# Read the README file
here = os.path.abspath(os.path.dirname(__file__))
try:
    with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = 'PyWatt SDK for Python - Build modules for the Wattson orchestrator'

setup(
    name='pywatt-sdk',
    version='0.3.0',
    description='PyWatt SDK for Python - Build modules for the Wattson orchestrator',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='PyWatt Team',
    author_email='pywatt@example.com',
    url='https://github.com/pywatt/pywatt-sdk-python',
    packages=find_packages(include=['*']),
    include_package_data=True,
    python_requires='>=3.8',
    install_requires=[
        'pydantic>=2.0.0',
        'typing-extensions>=4.0.0',
        'structlog>=23.1.0',
        'python-dotenv>=1.0.0',
        'httpx>=0.24.0',
        'websockets>=11.0.0',
        'orjson>=3.8.0',
        'cryptography>=41.0.0',
        'pyjwt>=2.8.0',
        'msgpack>=1.0.7',
    ],
    extras_require={
        'fastapi': [
            'fastapi>=0.100.0',
            'uvicorn[standard]>=0.23.0',
        ],
        'flask': [
            'flask>=2.3.0',
            'gunicorn>=21.0.0',
        ],
        'dev': [
            'pytest>=7.0.0',
            'pytest-asyncio>=0.21.0',
            'pytest-mock>=3.11.0',
            'black>=23.0.0',
            'isort>=5.12.0',
            'mypy>=1.4.0',
        ],
        'all': [
            'fastapi>=0.100.0',
            'uvicorn[standard]>=0.23.0',
            'flask>=2.3.0',
            'gunicorn>=21.0.0',
            'prometheus-client>=0.17.0',
            'psutil>=5.9.0',
            'anyio>=3.7.0',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Distributed Computing',
    ],
    keywords='pywatt wattson orchestrator microservices sdk',
    project_urls={
        'Documentation': 'https://pywatt.readthedocs.io',
        'Source': 'https://github.com/pywatt/pywatt-sdk-python',
        'Tracker': 'https://github.com/pywatt/pywatt-sdk-python/issues',
    },
) 