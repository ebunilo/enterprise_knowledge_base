"""
Configuration management for Canonical DB Agent.
Uses pydantic-settings for environment variable validation.
"""

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
    # Comma-separated keys accepted in X-API-Key for service-to-service calls.
    # Falls back to SECRET_KEY when unset so existing deployments keep working.
    service_api_keys: str = ""
    allowed_origins: str = "http://localhost:3000"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Monitoring
    metrics_enabled: bool = True

    # Performance
    query_timeout_ms: int = 5000
    bulk_insert_batch_size: int = 1000

    # Audit / privacy: store full query text in retrieval_audit_logs.
    # Off by default (AGENTS.md 5.16 compliance: hash is always stored).
    audit_store_query_text: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def api_keys(self) -> list[str]:
        """Accepted service API keys."""
        keys = [key.strip() for key in self.service_api_keys.split(",") if key.strip()]
        return keys or [self.secret_key]


# Global settings instance
settings = Settings()
