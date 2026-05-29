"""
Configuration management for Canonical DB Agent.
Uses pydantic-settings for environment variable validation.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "canonical-db-agent"
    environment: str = "production"
    debug: bool = False
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    api_reload: bool = False
    
    # Database Configuration
    database_url: str
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_echo: bool = False
    
    # Redis Configuration
    redis_url: str
    cache_ttl: int = 300  # 5 minutes
    
    # Security
    secret_key: str
    allowed_origins: str = "http://localhost:3000"
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Monitoring
    metrics_enabled: bool = True
    
    # Performance
    query_timeout_ms: int = 5000
    bulk_insert_batch_size: int = 1000
    
    # Row-Level Security
    rls_enabled: bool = True
    require_tenant_id: bool = True
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]


# Global settings instance
settings = Settings()

# Made with Bob
