"""JWT authentication middleware and FastAPI dependencies.

Tenant identity is derived from the JWT sub claim (tenant_id).
Schema isolation is enforced by setting PostgreSQL search_path per request.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.config import Settings, get_settings
from api.exceptions import TenantNotFoundError

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=True)


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable identity attached to every authenticated request."""

    tenant_id: str
    tenant_slug: str
    schema_name: str
    plan: str
    rate_limit_rpm: int


def _decode_token(token: str, settings: Settings) -> dict:
    """Decode and validate a JWT; raises HTTPException on any failure."""
    try:
        payload = jwt.decode(
            token,
            settings.api_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_tenant(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TenantContext:
    """FastAPI dependency — authenticates the bearer token and returns TenantContext.

    The JWT payload must contain:
      - sub: tenant_id (UUID string)
      - slug: tenant slug
      - schema: PostgreSQL schema name
      - plan: subscription plan
      - rpm: rate limit (requests per minute)
    """
    payload = _decode_token(credentials.credentials, settings)

    required = ("sub", "slug", "schema", "plan", "rpm")
    missing = [k for k in required if k not in payload]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token missing required claims: {missing}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TenantContext(
        tenant_id=payload["sub"],
        tenant_slug=payload["slug"],
        schema_name=payload["schema"],
        plan=payload["plan"],
        rate_limit_rpm=int(payload["rpm"]),
    )


async def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """FastAPI dependency — validates the static HARMONI_ADMIN_TOKEN.

    Used exclusively on tenant provisioning endpoints.
    """
    if credentials.credentials != settings.harmoni_admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )
