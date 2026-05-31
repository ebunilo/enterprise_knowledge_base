"""
Configuration management for Auth ACL Agent.

This module handles all configuration settings using pydantic-settings
for environment variable management.
"""

import logging
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Application
    environment: str = Field(default="development", description="Environment name")
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string"
    )
    
    # Database
    database_url: str = Field(..., description="PostgreSQL connection string")
    db_pool_size: int = Field(default=20, description="Database connection pool size")
    db_max_overflow: int = Field(default=10, description="Max overflow connections")
    db_pool_timeout: int = Field(default=30, description="Pool timeout in seconds")
    
    # Redis
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: str = Field(..., description="Redis password")
    redis_db: int = Field(default=0, description="Redis database number")
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds")
    
    # OIDC/OAuth2
    oidc_provider_url: str = Field(..., description="OIDC provider URL")
    oidc_client_id: str = Field(..., description="OIDC client ID")
    oidc_client_secret: str = Field(..., description="OIDC client secret")
    oidc_jwks_cache_ttl: int = Field(default=3600, description="JWKS cache TTL in seconds")
    
    # Security
    secret_key: str = Field(..., description="Application secret key")
    require_tenant_id: bool = Field(default=True, description="Require tenant ID in requests")
    strict_tenant_isolation: bool = Field(default=True, description="Enforce strict tenant isolation")
    log_access_denials: bool = Field(default=True, description="Log access denials")
    
    # CORS
    cors_origins: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins (comma-separated)"
    )
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Log level must be one of: {', '.join(valid_levels)}")
        return v_upper


# Global settings instance
settings = Settings()

# Note: Logging is configured in main.py to properly handle "json" vs "text" format
# Do not configure logging here to avoid conflicts

# Made with Bob
