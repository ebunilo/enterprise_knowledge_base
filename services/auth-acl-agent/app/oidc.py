"""
OIDC/OAuth2 client for token validation.

This module handles OIDC token validation, JWT parsing,
and user claims extraction from Keycloak.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import httpx
from jose import JWTError, jwt

from app.config import settings
from app.database import cache_get, cache_set

logger = logging.getLogger(__name__)


# ============================================================================
# OIDC Configuration
# ============================================================================

class OIDCConfig:
    """OIDC provider configuration."""
    
    def __init__(self):
        self.provider_url = settings.oidc_provider_url
        self.client_id = settings.oidc_client_id
        self.client_secret = settings.oidc_client_secret
        self.jwks_cache_ttl = settings.oidc_jwks_cache_ttl
        
        # Derived URLs
        self.well_known_url = f"{self.provider_url}/.well-known/openid-configuration"
        self.jwks_uri: Optional[str] = None
        self.issuer: Optional[str] = None
        self.authorization_endpoint: Optional[str] = None
        self.token_endpoint: Optional[str] = None
        self.userinfo_endpoint: Optional[str] = None
    
    async def load_configuration(self) -> bool:
        """
        Load OIDC provider configuration from well-known endpoint.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check cache first
            cache_key = f"oidc:config:{self.provider_url}"
            cached = cache_get(cache_key)
            
            if cached:
                config = json.loads(cached)
                self.jwks_uri = config["jwks_uri"]
                self.issuer = config["issuer"]
                self.authorization_endpoint = config.get("authorization_endpoint")
                self.token_endpoint = config.get("token_endpoint")
                self.userinfo_endpoint = config.get("userinfo_endpoint")
                logger.debug("Loaded OIDC configuration from cache")
                return True
            
            # Fetch from provider
            async with httpx.AsyncClient() as client:
                response = await client.get(self.well_known_url, timeout=10.0)
                response.raise_for_status()
                config = response.json()
            
            self.jwks_uri = config["jwks_uri"]
            self.issuer = config["issuer"]
            self.authorization_endpoint = config.get("authorization_endpoint")
            self.token_endpoint = config.get("token_endpoint")
            self.userinfo_endpoint = config.get("userinfo_endpoint")
            
            # Cache configuration
            cache_set(cache_key, json.dumps(config), ttl=3600)
            
            logger.info(f"Loaded OIDC configuration from {self.well_known_url}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load OIDC configuration: {e}")
            return False


# Global OIDC config instance
oidc_config = OIDCConfig()


# ============================================================================
# JWKS Management
# ============================================================================

async def get_jwks() -> Optional[Dict]:
    """
    Get JSON Web Key Set from OIDC provider.
    
    Returns:
        JWKS dictionary or None if failed
    """
    try:
        # Ensure configuration is loaded
        if not oidc_config.jwks_uri:
            await oidc_config.load_configuration()
        
        if not oidc_config.jwks_uri:
            logger.error("JWKS URI not available")
            return None
        
        # Check cache first
        cache_key = f"oidc:jwks:{oidc_config.provider_url}"
        cached = cache_get(cache_key)
        
        if cached:
            logger.debug("Loaded JWKS from cache")
            return json.loads(cached)
        
        # Fetch from provider
        async with httpx.AsyncClient() as client:
            response = await client.get(oidc_config.jwks_uri, timeout=10.0)
            response.raise_for_status()
            jwks = response.json()
        
        # Cache JWKS
        cache_set(cache_key, json.dumps(jwks), ttl=oidc_config.jwks_cache_ttl)
        
        logger.info("Fetched JWKS from provider")
        return jwks
        
    except Exception as e:
        logger.error(f"Failed to get JWKS: {e}")
        return None


# ============================================================================
# Token Validation
# ============================================================================

async def validate_token(token: str) -> Optional[Dict]:
    """
    Validate JWT token and extract claims.
    
    Args:
        token: JWT token string
        
    Returns:
        Token claims dictionary or None if invalid
    """
    try:
        # Get JWKS
        jwks = await get_jwks()
        if not jwks:
            logger.error("Cannot validate token: JWKS not available")
            return None
        
        # Decode token header to get key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            logger.warning("Token missing key ID (kid)")
            return None
        
        # Find matching key in JWKS
        key = None
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid:
                key = jwk
                break
        
        if not key:
            logger.warning(f"No matching key found for kid: {kid}")
            return None
        
        # Verify and decode token
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.oidc_client_id,
            issuer=oidc_config.issuer,
            options={
                "verify_signature": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True
            }
        )
        
        logger.debug(f"Token validated successfully for user: {claims.get('sub')}")
        return claims
        
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return None


async def validate_token_cached(token: str) -> Optional[Dict]:
    """
    Validate JWT token with caching.
    
    Args:
        token: JWT token string
        
    Returns:
        Token claims dictionary or None if invalid
    """
    try:
        # Create cache key from token hash
        import hashlib
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        cache_key = f"oidc:token:{token_hash}"
        
        # Check cache
        cached = cache_get(cache_key)
        if cached:
            logger.debug("Token validation result from cache")
            return json.loads(cached)
        
        # Validate token
        claims = await validate_token(token)
        
        if claims:
            # Cache valid token claims (short TTL for security)
            exp = claims.get("exp")
            if exp:
                # Cache until token expiry or max 5 minutes
                now = datetime.utcnow().timestamp()
                ttl = min(int(exp - now), 300)
                if ttl > 0:
                    cache_set(cache_key, json.dumps(claims), ttl=ttl)
        
        return claims
        
    except Exception as e:
        logger.error(f"Cached token validation error: {e}")
        return None


# ============================================================================
# User Claims Extraction
# ============================================================================

def extract_user_claims(token_claims: Dict) -> Dict:
    """
    Extract user claims from JWT token.
    
    Args:
        token_claims: Decoded JWT claims
        
    Returns:
        Normalized user claims dictionary
    """
    return {
        "user_id": token_claims.get("sub"),
        "email": token_claims.get("email"),
        "tenant_id": token_claims.get("tenant_id"),
        "department": token_claims.get("department"),
        "groups": token_claims.get("groups", []),
        "role": token_claims.get("role"),
        "region": token_claims.get("region"),
        "country": token_claims.get("country"),
        "clearance": token_claims.get("clearance", "INTERNAL_GENERAL"),
        "is_employee": token_claims.get("is_employee", True),
        "exp": token_claims.get("exp"),
        "iat": token_claims.get("iat")
    }


# ============================================================================
# Token Introspection (Optional)
# ============================================================================

async def introspect_token(token: str) -> Optional[Dict]:
    """
    Introspect token using OIDC introspection endpoint.
    
    This is an alternative to JWT validation for opaque tokens.
    
    Args:
        token: Token string
        
    Returns:
        Introspection result or None if failed
    """
    try:
        if not oidc_config.token_endpoint:
            await oidc_config.load_configuration()
        
        introspection_url = oidc_config.token_endpoint.replace("/token", "/introspect")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                introspection_url,
                data={
                    "token": token,
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret
                },
                timeout=10.0
            )
            response.raise_for_status()
            result = response.json()
        
        if result.get("active"):
            return result
        
        return None
        
    except Exception as e:
        logger.error(f"Token introspection failed: {e}")
        return None

# Made with Bob
