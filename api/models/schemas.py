"""Pydantic v2 request/response schemas for the harmoni REST API.

All responses roll up to the Account entity (domain key) — never return
contact-level data without account context (account-first rule).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------


class _BaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------


class FatigueComponentResponse(_BaseResponse):
    name: str
    score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(ge=0.0, le=1.0)
    weighted_score: float
    breakdown: dict[str, Any] = Field(default_factory=dict)


class FatigueScoreResponse(_BaseResponse):
    account_domain: str
    score: float = Field(ge=0.0, le=100.0)
    severity: str = Field(description="LOW | MEDIUM | HIGH | CRITICAL")
    components: list[FatigueComponentResponse] = Field(default_factory=list)
    is_over_threshold: bool
    computed_at: datetime


class IntentScoreResponse(_BaseResponse):
    account_domain: str
    intent_score: float = Field(ge=0.0, le=100.0, description="0–100 account-level intent score")
    confidence: float = Field(ge=0.0, le=1.0)
    computed_at: datetime


class ChurnPredictionResponse(_BaseResponse):
    account_domain: str
    churn_probability: float = Field(ge=0.0, le=1.0)
    risk_level: str = Field(description="LOW | MEDIUM | HIGH | CRITICAL")
    is_high_risk: bool
    signal_breakdown: dict[str, Any] = Field(default_factory=dict)
    computed_at: datetime


# ---------------------------------------------------------------------------
# Next Best Action
# ---------------------------------------------------------------------------


class NBAResponse(_BaseResponse):
    id: UUID
    account_domain: str
    action_type: str
    priority: int
    rationale: str
    fatigue_score: float
    intent_score: float
    churn_probability: float
    is_active: bool
    expires_at: datetime | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


class AccountProfileResponse(_BaseResponse):
    id: UUID
    domain: str
    display_name: str | None = None
    industry: str | None = None
    arr_usd: float | None = Field(None, description="Annual Recurring Revenue in USD")
    employee_count: int | None = None
    committee_size: int = Field(0, description="Number of tracked BuyingCommittee members")
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AccountSummaryResponse(_BaseResponse):
    """Composite view of an account's current health signals."""

    account: AccountProfileResponse
    fatigue: FatigueScoreResponse | None = None
    intent: IntentScoreResponse | None = None
    churn: ChurnPredictionResponse | None = None
    current_nba: NBAResponse | None = None


class AccountListResponse(_BaseResponse):
    items: list[AccountProfileResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    has_next: bool


# ---------------------------------------------------------------------------
# Signal ingestion
# ---------------------------------------------------------------------------


class SignalIngestRequest(BaseModel):
    member_email: str = Field(description="Email of the CommitteeMember emitting the signal")
    signal_type: str = Field(
        description=(
            "One of: email_open, email_click, email_reply, page_view, pricing_page_view, "
            "webinar_attend, video_view, crm_note, unsubscribe, spam_report, bounce"
        )
    )
    channel: str = Field(description="Source channel: email | web | webinar | crm | video")
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("member_email")
    @classmethod
    def email_not_empty(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("member_email must be a valid email address")
        return v.strip().lower()


class SignalIngestResponse(_BaseResponse):
    accepted: bool
    signal_id: UUID
    account_domain: str
    message: str = "Signal accepted for processing"


# ---------------------------------------------------------------------------
# Tenant management
# ---------------------------------------------------------------------------


class TenantCreateRequest(BaseModel):
    slug: str = Field(
        min_length=2,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$",
        description="URL-safe lowercase slug, e.g. 'acme-corp'",
    )
    display_name: str = Field(min_length=1, max_length=255)
    plan: str = Field(default="starter", pattern=r"^(starter|growth|enterprise)$")
    rate_limit_rpm: int = Field(default=60, ge=10, le=6000)


class TenantResponse(_BaseResponse):
    id: UUID
    slug: str
    display_name: str
    schema_name: str
    plan: str
    is_active: bool
    rate_limit_rpm: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Webhook management
# ---------------------------------------------------------------------------

_VALID_EVENT_TYPES = {
    "nba.created",
    "nba.superseded",
    "fatigue.critical",
    "fatigue.high",
    "cooldown.set",
    "cooldown.cleared",
    "churn.high",
    "churn.critical",
    "signal.ingested",
}


class WebhookRegisterRequest(BaseModel):
    target_url: str = Field(description="HTTPS URL that will receive POST payloads")
    description: str | None = Field(None, max_length=500)
    event_types: list[str] = Field(
        min_length=1, description="List of event types to subscribe to"
    )

    @field_validator("target_url")
    @classmethod
    def must_be_https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("target_url must use HTTPS")
        return v

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, v: list[str]) -> list[str]:
        invalid = set(v) - _VALID_EVENT_TYPES
        if invalid:
            raise ValueError(f"Unknown event types: {invalid}. Valid: {sorted(_VALID_EVENT_TYPES)}")
        return list(set(v))  # deduplicate


class WebhookResponse(_BaseResponse):
    id: UUID
    tenant_id: UUID
    target_url: str
    description: str | None = None
    event_types: list[str]
    is_active: bool
    failure_count: int
    last_success_at: datetime | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    error: str
    code: str
    request_id: str | None = None
    details: dict[str, Any] | None = None
