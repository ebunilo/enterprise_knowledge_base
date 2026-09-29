"""
Configuration management for Auth ACL Agent.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # Database
    database_url: str = Field(..., description="PostgreSQL connection string")
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # Redis (OIDC discovery/JWKS/token-claims cache only; never ACL decisions)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = Field(..., description="Redis password")
    redis_db: int = 0
    cache_ttl: int = 300

    # OIDC (Keycloak). OIDC_PROVIDER_URL must be the realm URL, e.g.
    # https://auth.igwilo.com/realms/enterprise-rag
    oidc_provider_url: str = Field(..., description="OIDC issuer / Keycloak realm URL")
    oidc_client_id: str = Field(..., description="OIDC client ID")
    oidc_client_secret: str = Field(..., description="OIDC client secret")
    oidc_jwks_cache_ttl: int = 3600
    # Accepted `aud` values (comma-separated). Defaults to the client ID.
    # Keycloak access tokens only carry the client in `aud` when an Audience
    # mapper is configured; otherwise they carry it in `azp`.
    oidc_audiences: str = ""
    oidc_accept_azp: bool = True
    oidc_algorithms: str = "RS256"

    # Access control
    # Groups whose members are never treated as employees (INTERNAL_GENERAL).
    external_groups: str = "external-users"
    # Require clearance >= classification for CONFIDENTIAL and above.
    enforce_clearance: bool = True
    log_access_denials: bool = True

    # CORS (comma-separated)
    allowed_origins: str = "http://localhost:3000"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Invalid log level")
        return v_upper

    @property
    def accepted_audiences(self) -> list[str]:
        return _csv(self.oidc_audiences) or [self.oidc_client_id]

    @property
    def allowed_algorithms(self) -> list[str]:
        return _csv(self.oidc_algorithms)

    @property
    def external_group_set(self) -> set[str]:
        return {group.lower().lstrip("/") for group in _csv(self.external_groups)}

    @property
    def cors_origins(self) -> list[str]:
        return _csv(self.allowed_origins)


settings = Settings()
