"""
Authentication endpoints (token validation and identity).

The login flow itself (authorization code + PKCE) is handled by the web UI
against Keycloak; this service only validates the resulting access tokens.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import claims_from_token, get_current_user
from app.oidc import validate_token
from app.schemas import TokenValidateRequest, TokenValidateResponse, UserClaims

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])


@router.post("/validate", response_model=TokenValidateResponse, summary="Validate an access token")
async def validate_token_endpoint(request: TokenValidateRequest, db: Session = Depends(get_db)):
    token_claims = await validate_token(request.token)
    if not token_claims:
        return TokenValidateResponse(valid=False, error="Invalid or expired token")
    try:
        return TokenValidateResponse(valid=True, claims=claims_from_token(token_claims, db))
    except HTTPException as e:
        return TokenValidateResponse(valid=False, error=e.detail)


@router.get("/user/me", response_model=UserClaims, summary="Current user")
@router.get("/user/info", response_model=UserClaims, summary="Current user (alias)")
def get_current_user_info(user: UserClaims = Depends(get_current_user)):
    return user
