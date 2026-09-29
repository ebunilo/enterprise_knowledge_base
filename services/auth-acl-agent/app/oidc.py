"""
OIDC (Keycloak) access-token validation.

A token is accepted only if:
  * it is signed by a key in the provider's JWKS with an allowed algorithm,
  * `iss` equals the discovered issuer and `exp` has not passed,
  * it is an access token (Keycloak `typ` = "Bearer"), not an ID token,
  * `aud` contains an accepted audience, or `azp` is the client (Keycloak
    access tokens do not include the client in `aud` unless an Audience
    mapper is configured).
"""

import hashlib
import json
import logging
import time
from typing import Dict, Optional

import httpx
from jose import JWTError, jwt

from app.config import settings
from app.database import cache_get, cache_set

logger = logging.getLogger(__name__)


class OIDCConfig:
    """OIDC provider configuration discovered from the well-known endpoint."""

    def __init__(self):
        self.provider_url = settings.oidc_provider_url.rstrip("/")
        self.well_known_url = f"{self.provider_url}/.well-known/openid-configuration"
        self.jwks_uri: Optional[str] = None
        self.issuer: Optional[str] = None
        self.token_endpoint: Optional[str] = None
        self.introspection_endpoint: Optional[str] = None

    def _apply(self, config: dict) -> None:
        self.jwks_uri = config["jwks_uri"]
        self.issuer = config["issuer"]
        self.token_endpoint = config.get("token_endpoint")
        self.introspection_endpoint = config.get("introspection_endpoint")

    async def load_configuration(self) -> bool:
        cache_key = f"oidc:config:{self.provider_url}"
        try:
            cached = cache_get(cache_key)
            if cached:
                self._apply(json.loads(cached))
                return True
            async with httpx.AsyncClient() as client:
                response = await client.get(self.well_known_url, timeout=10.0)
                response.raise_for_status()
                config = response.json()
            self._apply(config)
            cache_set(cache_key, json.dumps(config), ttl=3600)
            logger.info("Loaded OIDC configuration from %s", self.well_known_url)
            return True
        except Exception as e:
            logger.error("Failed to load OIDC configuration from %s: %s", self.well_known_url, e)
            return False


oidc_config = OIDCConfig()


async def get_jwks(force_refresh: bool = False) -> Optional[Dict]:
    """JSON Web Key Set, cached; `force_refresh` handles key rotation."""
    if not oidc_config.jwks_uri and not await oidc_config.load_configuration():
        return None
    cache_key = f"oidc:jwks:{oidc_config.provider_url}"
    try:
        if not force_refresh:
            cached = cache_get(cache_key)
            if cached:
                return json.loads(cached)
        async with httpx.AsyncClient() as client:
            response = await client.get(oidc_config.jwks_uri, timeout=10.0)
            response.raise_for_status()
            jwks = response.json()
        cache_set(cache_key, json.dumps(jwks), ttl=settings.oidc_jwks_cache_ttl)
        return jwks
    except Exception as e:
        logger.error("Failed to get JWKS: %s", e)
        return None


def _find_key(jwks: Optional[Dict], kid: str) -> Optional[Dict]:
    for key in (jwks or {}).get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


def _audience_ok(claims: Dict) -> bool:
    accepted = set(settings.accepted_audiences)
    aud = claims.get("aud")
    audiences = {aud} if isinstance(aud, str) else set(aud or [])
    if audiences & accepted:
        return True
    return settings.oidc_accept_azp and claims.get("azp") in accepted


async def validate_token(token: str) -> Optional[Dict]:
    """Validate an access token; returns its claims or None."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        logger.warning("Malformed token: %s", e)
        return None

    kid = header.get("kid")
    if not kid or header.get("alg") not in settings.allowed_algorithms:
        logger.warning("Token rejected: missing kid or disallowed alg %r", header.get("alg"))
        return None

    key = _find_key(await get_jwks(), kid)
    if key is None:
        # Keycloak rotated its keys since we cached the JWKS.
        key = _find_key(await get_jwks(force_refresh=True), kid)
    if key is None:
        logger.warning("No signing key found for kid %s", kid)
        return None

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=settings.allowed_algorithms,
            issuer=oidc_config.issuer,
            options={"verify_aud": False, "verify_exp": True, "verify_iss": True, "require_exp": True},
        )
    except JWTError as e:
        logger.warning("JWT validation failed: %s", e)
        return None

    if claims.get("typ") not in (None, "Bearer"):
        logger.warning("Token rejected: typ %r is not an access token", claims.get("typ"))
        return None
    if not _audience_ok(claims):
        logger.warning("Token rejected: audience %r / azp %r not accepted", claims.get("aud"), claims.get("azp"))
        return None
    return claims


async def validate_token_cached(token: str) -> Optional[Dict]:
    """validate_token with a short-lived cache keyed by the full token hash."""
    cache_key = f"oidc:token:{hashlib.sha256(token.encode()).hexdigest()}"
    cached = cache_get(cache_key)
    if cached:
        claims = json.loads(cached)
        if claims.get("exp", 0) > time.time():
            return claims

    claims = await validate_token(token)
    if claims:
        ttl = min(int(claims["exp"] - time.time()), 300)
        if ttl > 0:
            cache_set(cache_key, json.dumps(claims), ttl=ttl)
    return claims
