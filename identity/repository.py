"""Database access layer for the identity resolution engine.

Uses asyncpg directly (no ORM). All methods accept/return domain model objects
from identity.models. Sprint 4 will add SCD Type 2 snapshot views on top of
these base tables.

Inject these repositories into AsyncAccountResolver for testability — unit
tests swap them for in-memory stubs without touching the database.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg

from identity.models import (
    Account,
    AliasType,
    CommitteeMember,
    CRMAccountXRef,
    DomainAlias,
    FirmographicData,
    QuarantineEntry,
    ROLE_WEIGHTS,
    SeniorityLevel,
    infer_seniority,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Account Repository
# ---------------------------------------------------------------------------


class AccountRepository:
    """Read / write access to the accounts, domain_aliases, and crm_account_xref tables."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ------------------------------------------------------------------
    # Account lookup
    # ------------------------------------------------------------------

    async def get_by_domain(self, domain: str) -> Account | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM accounts WHERE domain = $1", domain
            )
        return _row_to_account(row) if row else None

    async def get_by_id(self, account_id: str) -> Account | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM accounts WHERE id = $1", account_id
            )
        return _row_to_account(row) if row else None

    # ------------------------------------------------------------------
    # Account creation / update
    # ------------------------------------------------------------------

    async def create_account(self, domain: str) -> Account:
        """Insert a new account record with minimal data; returns created Account."""
        account_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO accounts (id, domain, created_at, updated_at)
                VALUES ($1, $2, NOW(), NOW())
                ON CONFLICT (domain) DO UPDATE SET updated_at = NOW()
                RETURNING *
                """,
                account_id,
                domain,
            )
        if row is None:
            raise RuntimeError(f"Failed to create/upsert account for domain={domain!r}")
        return _row_to_account(row)  # type: ignore[arg-type]

    async def update_firmographic(
        self, domain: str, data: FirmographicData
    ) -> Account | None:
        """Write enriched firmographic data to an existing account row."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE accounts
                SET name                    = COALESCE($2, name),
                    industry                = COALESCE($3, industry),
                    employee_count          = COALESCE($4, employee_count),
                    arr_band                = COALESCE($5, arr_band),
                    country                 = COALESCE($6, country),
                    firmographic_source     = $7,
                    firmographic_enriched_at = $8,
                    raw_firmographic        = $9::jsonb,
                    updated_at              = NOW()
                WHERE domain = $1
                RETURNING *
                """,
                domain,
                data.name,
                data.industry,
                data.employee_count,
                data.arr_band,
                data.country,
                data.source,
                data.enriched_at,
                json.dumps(data.raw),
            )
        return _row_to_account(row) if row else None

    # ------------------------------------------------------------------
    # Alias table
    # ------------------------------------------------------------------

    async def get_alias(self, alias_domain: str) -> DomainAlias | None:
        """Look up an active alias for the given domain."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM domain_aliases
                WHERE alias_domain = $1
                  AND effective_from <= NOW()
                  AND (effective_to IS NULL OR effective_to > NOW())
                ORDER BY effective_from DESC
                LIMIT 1
                """,
                alias_domain,
            )
        return _row_to_alias(row) if row else None

    async def upsert_alias(
        self,
        alias_domain: str,
        canonical_domain: str,
        alias_type: AliasType = AliasType.MANUAL,
        note: str | None = None,
    ) -> DomainAlias:
        alias_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO domain_aliases
                    (id, alias_domain, canonical_domain, alias_type, note, effective_from)
                VALUES ($1, $2, $3, $4::alias_type, $5, NOW())
                ON CONFLICT (alias_domain, effective_from)
                DO UPDATE SET canonical_domain = $3, note = $5
                RETURNING *
                """,
                alias_id, alias_domain, canonical_domain, alias_type.value, note,
            )
        return _row_to_alias(row)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # CRM cross-reference
    # ------------------------------------------------------------------

    async def get_by_crm_id(
        self, crm_source: str, crm_company_id: str
    ) -> CRMAccountXRef | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM crm_account_xref
                WHERE crm_source = $1 AND crm_company_id = $2
                """,
                crm_source, crm_company_id,
            )
        return _row_to_crm_xref(row) if row else None

    async def upsert_crm_xref(
        self,
        canonical_domain: str,
        crm_source: str,
        crm_company_id: str,
        crm_company_name: str | None = None,
    ) -> CRMAccountXRef:
        xref_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO crm_account_xref
                    (id, canonical_domain, crm_source, crm_company_id, crm_company_name)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (crm_source, crm_company_id)
                DO UPDATE SET canonical_domain  = $2,
                              crm_company_name  = COALESCE($5, crm_account_xref.crm_company_name),
                              updated_at        = NOW()
                RETURNING *
                """,
                xref_id, canonical_domain, crm_source, crm_company_id, crm_company_name,
            )
        return _row_to_crm_xref(row)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Committee Member Repository
# ---------------------------------------------------------------------------


class CommitteeMemberRepository:
    """Read / write access to the committee_members table."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_by_email_and_account(
        self, email: str, account_id: str
    ) -> CommitteeMember | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM committee_members WHERE email = $1 AND account_id = $2",
                email, account_id,
            )
        return _row_to_member(row) if row else None

    async def get_members_for_account(
        self, account_id: str, *, active_only: bool = True
    ) -> list[CommitteeMember]:
        query = "SELECT * FROM committee_members WHERE account_id = $1"
        if active_only:
            query += " AND is_active = TRUE"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, account_id)
        return [_row_to_member(r) for r in rows]

    async def upsert_member(
        self,
        account_id: str,
        email: str,
        title: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        crm_contact_id: str | None = None,
        crm_source: str | None = None,
    ) -> CommitteeMember:
        seniority = infer_seniority(title)
        role_weight = ROLE_WEIGHTS[seniority]
        member_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO committee_members
                    (id, account_id, email, first_name, last_name, title,
                     seniority_level, role_weight, crm_contact_id, crm_source,
                     created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::seniority_level, $8, $9, $10, NOW(), NOW())
                ON CONFLICT (email, account_id)
                DO UPDATE SET
                    first_name      = COALESCE($4, committee_members.first_name),
                    last_name       = COALESCE($5, committee_members.last_name),
                    title           = COALESCE($6, committee_members.title),
                    seniority_level = $7::seniority_level,
                    role_weight     = $8,
                    crm_contact_id  = COALESCE($9, committee_members.crm_contact_id),
                    crm_source      = COALESCE($10, committee_members.crm_source),
                    updated_at      = NOW()
                RETURNING *
                """,
                member_id, account_id, email, first_name, last_name, title,
                seniority.value, float(role_weight), crm_contact_id, crm_source,
            )
        return _row_to_member(row)  # type: ignore[arg-type]

    async def touch_last_signal(self, member_id: str) -> None:
        """Update last_signal_at to now for a committee member."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE committee_members SET last_signal_at = NOW() WHERE id = $1",
                member_id,
            )


# ---------------------------------------------------------------------------
# Quarantine Repository
# ---------------------------------------------------------------------------


class QuarantineRepository:
    """Read / write access to resolution_quarantine table."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def enqueue(
        self,
        event_id: str,
        source_topic: str,
        raw_event: dict[str, Any],
        resolution_attempt: dict[str, Any],
        confidence: str,
    ) -> str:
        """Insert a quarantine entry; return its UUID."""
        qid = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO resolution_quarantine
                    (id, event_id, source_topic, raw_event, resolution_attempt, confidence)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::resolution_confidence)
                """,
                qid, event_id, source_topic,
                json.dumps(raw_event), json.dumps(resolution_attempt), confidence,
            )
        return qid

    async def list_pending(self, limit: int = 100) -> list[QuarantineEntry]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM resolution_quarantine
                WHERE status = 'PENDING'
                ORDER BY created_at
                LIMIT $1
                """,
                limit,
            )
        return [_row_to_quarantine(r) for r in rows]

    async def resolve(
        self, quarantine_id: str, canonical_domain: str, reviewer: str
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE resolution_quarantine
                SET status = 'RESOLVED', resolved_domain = $2,
                    reviewed_by = $3, reviewed_at = NOW()
                WHERE id = $1
                """,
                quarantine_id, canonical_domain, reviewer,
            )

    async def discard(self, quarantine_id: str, reviewer: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE resolution_quarantine
                SET status = 'DISCARDED', reviewed_by = $2, reviewed_at = NOW()
                WHERE id = $1
                """,
                quarantine_id, reviewer,
            )


# ---------------------------------------------------------------------------
# Row → model mappers
# ---------------------------------------------------------------------------


def _row_to_account(row: asyncpg.Record) -> Account:
    return Account(
        id=str(row["id"]),
        domain=row["domain"],
        name=row["name"],
        industry=row["industry"],
        employee_count=row["employee_count"],
        arr_band=row["arr_band"],
        country=row["country"],
        firmographic_source=row["firmographic_source"],
        firmographic_enriched_at=row["firmographic_enriched_at"],
        raw_firmographic=json.loads(row["raw_firmographic"] or "{}"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_alias(row: asyncpg.Record) -> DomainAlias:
    return DomainAlias(
        id=str(row["id"]),
        alias_domain=row["alias_domain"],
        canonical_domain=row["canonical_domain"],
        alias_type=AliasType(row["alias_type"]),
        note=row["note"],
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
        created_at=row["created_at"],
    )


def _row_to_member(row: asyncpg.Record) -> CommitteeMember:
    return CommitteeMember(
        id=str(row["id"]),
        account_id=str(row["account_id"]),
        email=row["email"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        title=row["title"],
        seniority_level=SeniorityLevel(row["seniority_level"]),
        role_weight=float(row["role_weight"]),
        crm_contact_id=row["crm_contact_id"],
        crm_source=row["crm_source"],
        is_active=row["is_active"],
        last_signal_at=row["last_signal_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_crm_xref(row: asyncpg.Record) -> CRMAccountXRef:
    return CRMAccountXRef(
        id=str(row["id"]),
        canonical_domain=row["canonical_domain"],
        crm_source=row["crm_source"],
        crm_company_id=row["crm_company_id"],
        crm_company_name=row["crm_company_name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_quarantine(row: asyncpg.Record) -> QuarantineEntry:
    return QuarantineEntry(
        id=str(row["id"]),
        event_id=row["event_id"],
        source_topic=row["source_topic"],
        raw_event=json.loads(row["raw_event"]),
        resolution_attempt=json.loads(row["resolution_attempt"]),
        confidence=row["confidence"],
        status=row["status"],
        reviewed_by=row["reviewed_by"],
        resolved_domain=row["resolved_domain"],
        reviewed_at=row["reviewed_at"],
        created_at=row["created_at"],
    )
