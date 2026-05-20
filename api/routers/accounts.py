"""Account endpoints — all roll up to the Account entity (domain key).

Endpoints:
  GET  /v1/accounts                       — paginated account list
  GET  /v1/accounts/{domain}              — full account summary
  GET  /v1/accounts/{domain}/fatigue      — latest fatigue score
  GET  /v1/accounts/{domain}/intent       — latest intent score
  GET  /v1/accounts/{domain}/nba          — current next best action
  POST /v1/accounts/{domain}/signals      — ingest a new intent signal
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.exceptions import AccountNotFoundError, InvalidDomainError
from api.middleware.auth import TenantContext, get_current_tenant
from api.models.schemas import (
    AccountListResponse,
    AccountProfileResponse,
    AccountSummaryResponse,
    ChurnPredictionResponse,
    FatigueScoreResponse,
    IntentScoreResponse,
    NBAResponse,
    SignalIngestRequest,
    SignalIngestResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/accounts", tags=["accounts"])

_Tenant = Annotated[TenantContext, Depends(get_current_tenant)]

_NOW = datetime(2024, 7, 1, tzinfo=timezone.utc)  # stub timestamp


def _normalize_domain(raw: str) -> str:
    """Lowercase and strip the domain; raises InvalidDomainError if empty."""
    domain = raw.strip().lower()
    if not domain or "." not in domain:
        raise InvalidDomainError(f"Invalid domain: {raw!r}")
    return domain


# ---------------------------------------------------------------------------
# Stub data helpers (replaced by real DB queries in production)
# ---------------------------------------------------------------------------

def _stub_account(domain: str, tenant: TenantContext) -> AccountProfileResponse:
    return AccountProfileResponse(
        id=uuid.uuid5(uuid.NAMESPACE_DNS, f"{tenant.tenant_id}:{domain}"),
        domain=domain,
        display_name=domain.split(".")[0].title(),
        industry="Technology",
        arr_usd=250000.0,
        employee_count=120,
        committee_size=5,
        is_active=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _stub_fatigue(domain: str) -> FatigueScoreResponse:
    return FatigueScoreResponse(
        account_domain=domain,
        score=42.0,
        severity="MEDIUM",
        components=[],
        is_over_threshold=False,
        computed_at=_NOW,
    )


def _stub_intent(domain: str) -> IntentScoreResponse:
    return IntentScoreResponse(
        account_domain=domain,
        intent_score=67.5,
        confidence=0.82,
        computed_at=_NOW,
    )


def _stub_churn(domain: str) -> ChurnPredictionResponse:
    return ChurnPredictionResponse(
        account_domain=domain,
        churn_probability=0.18,
        risk_level="LOW",
        is_high_risk=False,
        signal_breakdown={},
        computed_at=_NOW,
    )


def _stub_nba(domain: str, tenant: TenantContext) -> NBAResponse:
    return NBAResponse(
        id=uuid.uuid5(uuid.NAMESPACE_DNS, f"{tenant.tenant_id}:{domain}:nba"),
        account_domain=domain,
        action_type="NURTURE",
        priority=7,
        rationale="Default nurture — no high-urgency signals detected",
        fatigue_score=42.0,
        intent_score=67.5,
        churn_probability=0.18,
        is_active=True,
        expires_at=None,
        created_at=_NOW,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    tenant: _Tenant,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> AccountListResponse:
    """Return a paginated list of accounts for the authenticated tenant."""
    stub_domains = ["acme.com", "globex.com", "initech.com"]
    items = [_stub_account(d, tenant) for d in stub_domains]
    return AccountListResponse(
        items=items,
        total=len(items),
        page=page,
        page_size=page_size,
        has_next=False,
    )


@router.get("/{domain}", response_model=AccountSummaryResponse)
async def get_account(domain: str, tenant: _Tenant) -> AccountSummaryResponse:
    """Return the full health summary for one account (fatigue + intent + churn + NBA)."""
    try:
        norm = _normalize_domain(domain)
    except InvalidDomainError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return AccountSummaryResponse(
        account=_stub_account(norm, tenant),
        fatigue=_stub_fatigue(norm),
        intent=_stub_intent(norm),
        churn=_stub_churn(norm),
        current_nba=_stub_nba(norm, tenant),
    )


@router.get("/{domain}/fatigue", response_model=FatigueScoreResponse)
async def get_fatigue(domain: str, tenant: _Tenant) -> FatigueScoreResponse:
    """Return the latest Account Fatigue Score."""
    try:
        norm = _normalize_domain(domain)
    except InvalidDomainError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return _stub_fatigue(norm)


@router.get("/{domain}/intent", response_model=IntentScoreResponse)
async def get_intent(domain: str, tenant: _Tenant) -> IntentScoreResponse:
    """Return the latest Intent Score for the account."""
    try:
        norm = _normalize_domain(domain)
    except InvalidDomainError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return _stub_intent(norm)


@router.get("/{domain}/nba", response_model=NBAResponse)
async def get_nba(domain: str, tenant: _Tenant) -> NBAResponse:
    """Return the active Next Best Action for the account."""
    try:
        norm = _normalize_domain(domain)
    except InvalidDomainError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return _stub_nba(norm, tenant)


@router.post(
    "/{domain}/signals",
    response_model=SignalIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_signal(
    domain: str,
    body: SignalIngestRequest,
    tenant: _Tenant,
) -> SignalIngestResponse:
    """Accept an intent signal for asynchronous processing via the CEP pipeline."""
    try:
        norm = _normalize_domain(domain)
    except InvalidDomainError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    signal_id = uuid.uuid4()
    logger.info(
        "Signal ingested: tenant=%s domain=%s signal_id=%s type=%s",
        tenant.tenant_slug,
        norm,
        signal_id,
        body.signal_type,
    )

    return SignalIngestResponse(
        accepted=True,
        signal_id=signal_id,
        account_domain=norm,
        message="Signal accepted for processing",
    )
