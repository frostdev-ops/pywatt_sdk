"""JWT Authentication middleware for PyWatt modules.

This module provides JWT authentication middleware for popular Python web frameworks.
It allows you to validate JWT tokens in the `Authorization: Bearer <token>` header
and extract claims into request context.

The middleware can be used either with typed claims for strong typing,
or with dynamic types for flexibility.
"""

import json
import logging
from typing import Dict, Any, Optional, Type, TypeVar, Generic, Callable, Awaitable
from dataclasses import dataclass
import jwt
from jwt.exceptions import InvalidTokenError

try:
    from core.error import AuthenticationError
except ImportError:
    class AuthenticationError(Exception):
        pass

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class JwtConfig:
    """JWT configuration."""
    secret_key: str
    algorithm: str = "HS256"
    verify_exp: bool = True
    verify_aud: bool = False
    verify_iss: bool = False
    audience: Optional[str] = None
    issuer: Optional[str] = None


class JwtAuthError(AuthenticationError):
    """JWT authentication error."""
    pass


class JwtValidator(Generic[T]):
    """JWT token validator."""
    
    def __init__(self, config: JwtConfig, claims_type: Optional[Type[T]] = None):
        """Initialize the JWT validator."""
        self.config = config
        self.claims_type = claims_type or dict
    
    def validate_token(self, token: str) -> T:
        """Validate a JWT token and return claims."""
        try:
            # Decode the token
            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                verify=True,
                options={
                    "verify_exp": self.config.verify_exp,
                    "verify_aud": self.config.verify_aud,
                    "verify_iss": self.config.verify_iss,
                },
                audience=self.config.audience,
                issuer=self.config.issuer
            )
            
            # Convert to the desired type
            if self.claims_type == dict:
                return payload
            else:
                # For typed claims, we'd need a proper conversion mechanism
                # For now, just return the payload
                return payload
        
        except InvalidTokenError as e:
            raise JwtAuthError(f"Invalid JWT token: {e}")
        except Exception as e:
            raise JwtAuthError(f"JWT validation failed: {e}")
    
    def extract_token_from_header(self, authorization_header: Optional[str]) -> str:
        """Extract JWT token from Authorization header."""
        if not authorization_header:
            raise JwtAuthError("Missing Authorization header")
        
        if not authorization_header.startswith("Bearer "):
            raise JwtAuthError("Authorization header must start with 'Bearer '")
        
        token = authorization_header[7:]  # Remove "Bearer " prefix
        if not token:
            raise JwtAuthError("Empty token in Authorization header")
        
        return token


# FastAPI Integration

try:
    from fastapi import Request, HTTPException, status
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    
    class FastAPIJwtMiddleware(BaseHTTPMiddleware):
        """FastAPI JWT authentication middleware."""
        
        def __init__(self, app, config: JwtConfig, claims_type: Optional[Type[T]] = None):
            """Initialize the FastAPI JWT middleware."""
            super().__init__(app)
            self.validator = JwtValidator(config, claims_type)
        
        async def dispatch(self, request: Request, call_next):
            """Process the request and validate JWT if present."""
            # Skip validation for certain paths
            if self._should_skip_validation(request):
                return await call_next(request)
            
            try:
                # Extract token from Authorization header
                auth_header = request.headers.get("Authorization")
                token = self.validator.extract_token_from_header(auth_header)
                
                # Validate token and extract claims
                claims = self.validator.validate_token(token)
                
                # Add claims to request state
                request.state.jwt_claims = claims
                
                return await call_next(request)
            
            except JwtAuthError as e:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"error": str(e)}
                )
            except Exception as e:
                logger.error(f"JWT middleware error: {e}")
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"error": "Internal server error"}
                )
        
        def _should_skip_validation(self, request: Request) -> bool:
            """Check if JWT validation should be skipped for this request."""
            # Skip for health checks and other public endpoints
            public_paths = ["/health", "/metrics", "/docs", "/openapi.json"]
            return request.url.path in public_paths
    
    
    def get_jwt_claims(request: Request) -> Dict[str, Any]:
        """Get JWT claims from FastAPI request."""
        if not hasattr(request.state, 'jwt_claims'):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No JWT claims found"
            )
        return request.state.jwt_claims
    
    
    def require_jwt_claims(request: Request) -> Dict[str, Any]:
        """Dependency to require JWT claims in FastAPI endpoints."""
        return get_jwt_claims(request)

except ImportError:
    # FastAPI not available
    FastAPIJwtMiddleware = None
    get_jwt_claims = None
    require_jwt_claims = None


# Flask Integration

try:
    from flask import Flask, request, g, jsonify
    from functools import wraps
    
    class FlaskJwtManager:
        """Flask JWT authentication manager."""
        
        def __init__(self, app: Optional[Flask] = None, config: Optional[JwtConfig] = None):
            """Initialize the Flask JWT manager."""
            self.config = config
            self.validator = None
            if app:
                self.init_app(app, config)
        
        def init_app(self, app: Flask, config: Optional[JwtConfig] = None):
            """Initialize the Flask app with JWT authentication."""
            if config:
                self.config = config
            
            if not self.config:
                raise ValueError("JWT config is required")
            
            self.validator = JwtValidator(self.config)
            
            # Register error handlers
            @app.errorhandler(JwtAuthError)
            def handle_jwt_error(error):
                return jsonify({"error": str(error)}), 401
        
        def jwt_required(self, f):
            """Decorator to require JWT authentication."""
            @wraps(f)
            def decorated_function(*args, **kwargs):
                try:
                    # Extract token from Authorization header
                    auth_header = request.headers.get("Authorization")
                    token = self.validator.extract_token_from_header(auth_header)
                    
                    # Validate token and extract claims
                    claims = self.validator.validate_token(token)
                    
                    # Store claims in Flask's g object
                    g.jwt_claims = claims
                    
                    return f(*args, **kwargs)
                
                except JwtAuthError as e:
                    return jsonify({"error": str(e)}), 401
                except Exception as e:
                    logger.error(f"JWT authentication error: {e}")
                    return jsonify({"error": "Authentication failed"}), 401
            
            return decorated_function
        
        def get_jwt_claims(self) -> Dict[str, Any]:
            """Get JWT claims from Flask's g object."""
            if not hasattr(g, 'jwt_claims'):
                raise JwtAuthError("No JWT claims found")
            return g.jwt_claims

except ImportError:
    # Flask not available
    FlaskJwtManager = None


# Starlette Integration

try:
    from starlette.applications import Starlette
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse
    
    class StarletteJwtMiddleware(BaseHTTPMiddleware):
        """Starlette JWT authentication middleware."""
        
        def __init__(self, app, config: JwtConfig, claims_type: Optional[Type[T]] = None):
            """Initialize the Starlette JWT middleware."""
            super().__init__(app)
            self.validator = JwtValidator(config, claims_type)
        
        async def dispatch(self, request: StarletteRequest, call_next):
            """Process the request and validate JWT if present."""
            # Skip validation for certain paths
            if self._should_skip_validation(request):
                return await call_next(request)
            
            try:
                # Extract token from Authorization header
                auth_header = request.headers.get("Authorization")
                token = self.validator.extract_token_from_header(auth_header)
                
                # Validate token and extract claims
                claims = self.validator.validate_token(token)
                
                # Add claims to request state
                request.state.jwt_claims = claims
                
                return await call_next(request)
            
            except JwtAuthError as e:
                return JSONResponse(
                    status_code=401,
                    content={"error": str(e)}
                )
            except Exception as e:
                logger.error(f"JWT middleware error: {e}")
                return JSONResponse(
                    status_code=500,
                    content={"error": "Internal server error"}
                )
        
        def _should_skip_validation(self, request: StarletteRequest) -> bool:
            """Check if JWT validation should be skipped for this request."""
            # Skip for health checks and other public endpoints
            public_paths = ["/health", "/metrics"]
            return request.url.path in public_paths

except ImportError:
    # Starlette not available
    StarletteJwtMiddleware = None


# Generic HTTP request/response JWT validation

def validate_jwt_from_headers(
    headers: Dict[str, str],
    config: JwtConfig,
    claims_type: Optional[Type[T]] = None
) -> T:
    """Validate JWT from HTTP headers."""
    validator = JwtValidator(config, claims_type)
    auth_header = headers.get("Authorization") or headers.get("authorization")
    token = validator.extract_token_from_header(auth_header)
    return validator.validate_token(token)


def create_jwt_token(claims: Dict[str, Any], config: JwtConfig) -> str:
    """Create a JWT token with the given claims."""
    return jwt.encode(
        claims,
        config.secret_key,
        algorithm=config.algorithm
    )


# Utility functions

def is_running_as_module() -> bool:
    """Check if running as a PyWatt module."""
    import os
    return "PYWATT_MODULE_ID" in os.environ


def get_jwt_secret_from_env() -> Optional[str]:
    """Get JWT secret from environment variables."""
    import os
    return os.getenv("JWT_SECRET") or os.getenv("PYWATT_JWT_SECRET")


def create_default_jwt_config(secret_key: Optional[str] = None) -> JwtConfig:
    """Create a default JWT configuration."""
    if not secret_key:
        secret_key = get_jwt_secret_from_env()
    
    if not secret_key:
        raise ValueError("JWT secret key is required")
    
    return JwtConfig(secret_key=secret_key) 