"""
Authentication API endpoints.

This module provides endpoints for token validation, user information,
and OIDC callback handling.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user, get_optional_user
from app.oidc import extract_user_claims, validate_token
from app.schemas import (
    TokenValidateRequest,
    TokenValidateResponse,
    UserClaims,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# ============================================================================
# Token Validation Endpoints
# ============================================================================

@router.post(
    "/validate",
    response_model=TokenValidateResponse,
    summary="Validate JWT token",
    description="Validate a JWT token and return user claims",
    tags=["Authentication"]
)
async def validate_token_endpoint(request: TokenValidateRequest):
    """
    Validate JWT token and return user claims.
    
    Args:
        request: Token validation request
        
    Returns:
        TokenValidateResponse with validation result and claims
    """
    try:
        logger.debug("Validating token")
        
        # Validate token
        token_claims = await validate_token(request.token)
        
        if not token_claims:
            return TokenValidateResponse(
                valid=False,
                claims=None,
                error="Invalid or expired token"
            )
        
        # Extract user claims
        user_claims_dict = extract_user_claims(token_claims)
        user_claims = UserClaims(**user_claims_dict)
        
        logger.info(f"Token validated successfully for user: {user_claims.user_id}")
        
        return TokenValidateResponse(
            valid=True,
            claims=user_claims,
            error=None
        )
        
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return TokenValidateResponse(
            valid=False,
            claims=None,
            error=str(e)
        )


# ============================================================================
# User Information Endpoints
# ============================================================================

@router.get(
    "/user/info",
    response_model=UserClaims,
    summary="Get user information",
    description="Get user information from authenticated token",
    tags=["Authentication"]
)
async def get_user_info(
    user_claims: UserClaims = Depends(get_current_user)
):
    """
    Get user information from authenticated token.
    
    Args:
        user_claims: User claims from token (injected by dependency)
        
    Returns:
        UserClaims object
    """
    logger.debug(f"Getting user info for: {user_claims.user_id}")
    return user_claims


@router.get(
    "/user/me",
    response_model=UserClaims,
    summary="Get current user",
    description="Get current authenticated user information",
    tags=["Authentication"]
)
async def get_current_user_info(
    user_claims: UserClaims = Depends(get_current_user)
):
    """
    Get current authenticated user information.
    
    This is an alias for /user/info for convenience.
    
    Args:
        user_claims: User claims from token (injected by dependency)
        
    Returns:
        UserClaims object
    """
    return user_claims


# ============================================================================
# OIDC Callback Endpoint
# ============================================================================

@router.post(
    "/callback",
    summary="OIDC callback handler",
    description="Handle OIDC authentication callback",
    tags=["Authentication"]
)
async def oidc_callback(
    code: str,
    state: str = None
):
    """
    Handle OIDC authentication callback.
    
    This endpoint receives the authorization code from the OIDC provider
    and exchanges it for tokens.
    
    Args:
        code: Authorization code from OIDC provider
        state: State parameter for CSRF protection
        
    Returns:
        Token response
        
    Note:
        This is a placeholder for MVP. Full OIDC flow implementation
        should be added in production.
    """
    logger.info(f"OIDC callback received with code: {code[:10]}...")
    
    # TODO: Implement full OIDC callback flow
    # 1. Validate state parameter
    # 2. Exchange code for tokens
    # 3. Validate tokens
    # 4. Create session
    # 5. Return tokens or redirect
    
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="OIDC callback not fully implemented in MVP"
    )


# ============================================================================
# Logout Endpoint
# ============================================================================

@router.post(
    "/logout",
    summary="Logout",
    description="Logout and invalidate token",
    tags=["Authentication"]
)
async def logout(
    user_claims: UserClaims = Depends(get_optional_user)
):
    """
    Logout and invalidate token.
    
    Args:
        user_claims: User claims from token (optional)
        
    Returns:
        Logout confirmation
        
    Note:
        This is a placeholder for MVP. Full logout implementation
        with token revocation should be added in production.
    """
    if user_claims:
        logger.info(f"User logout: {user_claims.user_id}")
        # TODO: Implement token revocation
        # 1. Invalidate token in cache
        # 2. Revoke token with OIDC provider
        # 3. Clear session
    
    return {
        "message": "Logged out successfully",
        "timestamp": "2026-05-29T11:19:00Z"
    }

# Made with Bob
