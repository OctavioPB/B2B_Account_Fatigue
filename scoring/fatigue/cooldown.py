"""ActionCooldownEngine — Redis-backed outreach cooldown management.

Cooldowns are enforced at two granularities:
  - Account level: all outreach to the account is paused.
  - Member level:  only outreach to a specific committee member is paused.

Redis key schema:
  cooldown:account:{account_id}   → severity value (e.g. "HIGH")
  cooldown:member:{member_id}     → severity value (e.g. "CRITICAL")

TTL is set at write time and drives the key expiry:
  LOW       24 hours   (86 400 s)
  MEDIUM    72 hours   (259 200 s)
  HIGH       7 days    (604 800 s)
  CRITICAL  30 days    (2 592 000 s)

Redis failure policy:
  - Writes (set/clear): raise — a silent write failure would allow over-contact,
    which is a product safety violation.
  - Reads (is_on_cooldown, get_cooldown_info): default to True / return sentinel
    on Redis failure — fail safe: assume cooldown is active rather than allow
    spurious outreach during a Redis outage.
"""

from __future__ import annotations

import logging
from typing import Any

from scoring.models import CooldownEntry, FatigueSeverity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTL mapping
# ---------------------------------------------------------------------------

COOLDOWN_TTL_SECONDS: dict[FatigueSeverity, int] = {
    FatigueSeverity.LOW:      86_400,       # 24 h
    FatigueSeverity.MEDIUM:   259_200,      # 72 h
    FatigueSeverity.HIGH:     604_800,      # 7 d
    FatigueSeverity.CRITICAL: 2_592_000,    # 30 d
}

# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

_PREFIX_ACCOUNT = "cooldown:account:"
_PREFIX_MEMBER  = "cooldown:member:"


def _account_key(account_id: str) -> str:
    return f"{_PREFIX_ACCOUNT}{account_id}"


def _member_key(member_id: str) -> str:
    return f"{_PREFIX_MEMBER}{member_id}"


# ---------------------------------------------------------------------------
# ActionCooldownEngine
# ---------------------------------------------------------------------------


class ActionCooldownEngine:
    """Manage per-account and per-member outreach cooldown locks in Redis.

    Args:
        redis_client: Any Redis-compatible client exposing ``set``, ``get``,
            ``delete``, and ``ttl`` methods (redis-py or fakeredis work).
    """

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Account-level cooldowns
    # ------------------------------------------------------------------

    def set_account_cooldown(
        self,
        account_id: str,
        severity: FatigueSeverity,
    ) -> int:
        """Set a cooldown lock for an entire account.

        Args:
            account_id: Account UUID string.
            severity:   Fatigue severity that triggered this cooldown.

        Returns:
            TTL in seconds that was applied.

        Raises:
            Exception: Propagated from Redis — caller must handle or alert.
        """
        ttl = COOLDOWN_TTL_SECONDS[severity]
        key = _account_key(account_id)
        self._redis.set(key, severity.value, ex=ttl)
        logger.info(
            "Account cooldown SET account=%s severity=%s ttl=%ds",
            account_id, severity.value, ttl,
        )
        return ttl

    def clear_account_cooldown(self, account_id: str) -> bool:
        """Remove an account cooldown lock.

        Returns:
            True if a lock existed and was deleted; False if none was set.

        Raises:
            Exception: Propagated from Redis.
        """
        key = _account_key(account_id)
        deleted = bool(self._redis.delete(key))
        if deleted:
            logger.info("Account cooldown CLEARED account=%s", account_id)
        return deleted

    def is_account_on_cooldown(self, account_id: str) -> bool:
        """Return True if the account has an active cooldown lock.

        Defaults to True on Redis failure (fail-safe: assume cooldown is active
        rather than risk over-contacting a fatigued account).
        """
        try:
            return self._redis.get(_account_key(account_id)) is not None
        except Exception:
            logger.error(
                "Redis read error for account cooldown check account=%s — "
                "defaulting to True (cooldown assumed active)",
                account_id,
                exc_info=True,
            )
            return True

    def get_account_cooldown_info(self, account_id: str) -> CooldownEntry | None:
        """Return CooldownEntry if the account is on cooldown, else None.

        Defaults to None on Redis read failure (logged; caller should treat
        as if cooldown is unknown and err on the side of caution).
        """
        try:
            key = _account_key(account_id)
            value = self._redis.get(key)
            if value is None:
                return None
            ttl = self._redis.ttl(key)
            severity_str = value.decode() if isinstance(value, bytes) else value
            return CooldownEntry(
                entity_type="account",
                entity_id=account_id,
                severity=FatigueSeverity(severity_str),
                ttl_seconds=max(0, ttl),
            )
        except Exception:
            logger.error(
                "Redis read error for account cooldown info account=%s",
                account_id,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Member-level cooldowns
    # ------------------------------------------------------------------

    def set_member_cooldown(
        self,
        member_id: str,
        severity: FatigueSeverity,
    ) -> int:
        """Set a cooldown lock for one committee member.

        Returns:
            TTL in seconds that was applied.

        Raises:
            Exception: Propagated from Redis.
        """
        ttl = COOLDOWN_TTL_SECONDS[severity]
        key = _member_key(member_id)
        self._redis.set(key, severity.value, ex=ttl)
        logger.info(
            "Member cooldown SET member=%s severity=%s ttl=%ds",
            member_id, severity.value, ttl,
        )
        return ttl

    def clear_member_cooldown(self, member_id: str) -> bool:
        """Remove a member cooldown lock.

        Returns:
            True if a lock existed and was deleted.

        Raises:
            Exception: Propagated from Redis.
        """
        key = _member_key(member_id)
        deleted = bool(self._redis.delete(key))
        if deleted:
            logger.info("Member cooldown CLEARED member=%s", member_id)
        return deleted

    def is_member_on_cooldown(self, member_id: str) -> bool:
        """Return True if the member has an active cooldown lock.

        Defaults to True on Redis failure (fail-safe).
        """
        try:
            return self._redis.get(_member_key(member_id)) is not None
        except Exception:
            logger.error(
                "Redis read error for member cooldown check member=%s — "
                "defaulting to True",
                member_id,
                exc_info=True,
            )
            return True

    def get_member_cooldown_info(self, member_id: str) -> CooldownEntry | None:
        """Return CooldownEntry if the member is on cooldown, else None."""
        try:
            key = _member_key(member_id)
            value = self._redis.get(key)
            if value is None:
                return None
            ttl = self._redis.ttl(key)
            severity_str = value.decode() if isinstance(value, bytes) else value
            return CooldownEntry(
                entity_type="member",
                entity_id=member_id,
                severity=FatigueSeverity(severity_str),
                ttl_seconds=max(0, ttl),
            )
        except Exception:
            logger.error(
                "Redis read error for member cooldown info member=%s",
                member_id,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Batch helpers (used by the Airflow DAG)
    # ------------------------------------------------------------------

    def apply_fatigue_score(
        self,
        account_id: str,
        fatigue_score: "Any",
    ) -> dict[str, Any]:
        """Apply or clear account cooldown based on a freshly computed fatigue score.

        Sets a cooldown if severity is HIGH or CRITICAL.
        Clears any existing cooldown if severity dropped to LOW or MEDIUM.

        Returns:
            Dict with keys: {"action": "set" | "cleared" | "no_change", "ttl": int | None}
        """
        from scoring.models import AccountFatigueScore

        if not isinstance(fatigue_score, AccountFatigueScore):
            raise TypeError(f"Expected AccountFatigueScore, got {type(fatigue_score)}")

        was_on_cooldown = self.is_account_on_cooldown(account_id)
        should_be_on    = fatigue_score.is_over_threshold

        if should_be_on:
            ttl = self.set_account_cooldown(account_id, fatigue_score.severity)
            return {"action": "set", "ttl": ttl, "severity": fatigue_score.severity.value}
        elif was_on_cooldown:
            self.clear_account_cooldown(account_id)
            return {"action": "cleared", "ttl": None, "severity": None}
        else:
            return {"action": "no_change", "ttl": None, "severity": None}
