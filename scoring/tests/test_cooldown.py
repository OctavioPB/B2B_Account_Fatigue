"""Tests for scoring.fatigue.cooldown — ActionCooldownEngine (Redis-backed).

Uses fakeredis for in-process testing — no live Redis required.
"""

from __future__ import annotations

import time

import pytest

try:
    import fakeredis

    _FAKEREDIS_AVAILABLE = True
except ImportError:
    _FAKEREDIS_AVAILABLE = False

from scoring.fatigue.cooldown import (
    ActionCooldownEngine,
    COOLDOWN_TTL_SECONDS,
    _account_key,
    _member_key,
)
from scoring.models import CooldownEntry, FatigueSeverity

pytestmark = pytest.mark.skipif(
    not _FAKEREDIS_AVAILABLE,
    reason="fakeredis not installed — run `uv add fakeredis --dev`",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def redis():
    return fakeredis.FakeRedis()


@pytest.fixture()
def engine(redis) -> ActionCooldownEngine:
    return ActionCooldownEngine(redis)


# ---------------------------------------------------------------------------
# TTL constants
# ---------------------------------------------------------------------------


class TestCooldownTTLConstants:
    @pytest.mark.parametrize("severity,expected_seconds", [
        (FatigueSeverity.LOW,      86_400),
        (FatigueSeverity.MEDIUM,   259_200),
        (FatigueSeverity.HIGH,     604_800),
        (FatigueSeverity.CRITICAL, 2_592_000),
    ])
    def test_ttl_values(self, severity, expected_seconds):
        assert COOLDOWN_TTL_SECONDS[severity] == expected_seconds


# ---------------------------------------------------------------------------
# Account cooldowns — set / check / clear
# ---------------------------------------------------------------------------


class TestAccountCooldown:
    def test_not_on_cooldown_by_default(self, engine):
        assert engine.is_account_on_cooldown("acct-1") is False

    def test_set_cooldown_returns_ttl(self, engine):
        ttl = engine.set_account_cooldown("acct-1", FatigueSeverity.HIGH)
        assert ttl == COOLDOWN_TTL_SECONDS[FatigueSeverity.HIGH]

    def test_is_on_cooldown_after_set(self, engine):
        engine.set_account_cooldown("acct-1", FatigueSeverity.MEDIUM)
        assert engine.is_account_on_cooldown("acct-1") is True

    def test_clear_removes_cooldown(self, engine):
        engine.set_account_cooldown("acct-1", FatigueSeverity.HIGH)
        engine.clear_account_cooldown("acct-1")
        assert engine.is_account_on_cooldown("acct-1") is False

    def test_clear_returns_true_when_was_set(self, engine):
        engine.set_account_cooldown("acct-1", FatigueSeverity.LOW)
        assert engine.clear_account_cooldown("acct-1") is True

    def test_clear_returns_false_when_not_set(self, engine):
        assert engine.clear_account_cooldown("acct-never-set") is False

    def test_different_accounts_independent(self, engine):
        engine.set_account_cooldown("acct-1", FatigueSeverity.HIGH)
        assert engine.is_account_on_cooldown("acct-2") is False

    def test_overwrite_cooldown_updates_severity(self, engine, redis):
        engine.set_account_cooldown("acct-1", FatigueSeverity.LOW)
        engine.set_account_cooldown("acct-1", FatigueSeverity.CRITICAL)
        value = redis.get(_account_key("acct-1"))
        assert value.decode() == FatigueSeverity.CRITICAL.value

    def test_overwrite_cooldown_updates_ttl(self, engine, redis):
        engine.set_account_cooldown("acct-1", FatigueSeverity.LOW)
        engine.set_account_cooldown("acct-1", FatigueSeverity.CRITICAL)
        ttl = redis.ttl(_account_key("acct-1"))
        assert ttl == pytest.approx(COOLDOWN_TTL_SECONDS[FatigueSeverity.CRITICAL], abs=2)


# ---------------------------------------------------------------------------
# Account cooldowns — get_account_cooldown_info
# ---------------------------------------------------------------------------


class TestGetAccountCooldownInfo:
    def test_returns_none_when_not_set(self, engine):
        assert engine.get_account_cooldown_info("acct-x") is None

    def test_returns_entry_when_set(self, engine):
        engine.set_account_cooldown("acct-1", FatigueSeverity.HIGH)
        entry = engine.get_account_cooldown_info("acct-1")
        assert isinstance(entry, CooldownEntry)
        assert entry.entity_type == "account"
        assert entry.entity_id == "acct-1"
        assert entry.severity == FatigueSeverity.HIGH

    def test_ttl_is_positive(self, engine):
        engine.set_account_cooldown("acct-1", FatigueSeverity.MEDIUM)
        entry = engine.get_account_cooldown_info("acct-1")
        assert entry is not None
        assert entry.ttl_seconds > 0

    def test_ttl_does_not_exceed_configured(self, engine):
        engine.set_account_cooldown("acct-1", FatigueSeverity.MEDIUM)
        entry = engine.get_account_cooldown_info("acct-1")
        assert entry is not None
        assert entry.ttl_seconds <= COOLDOWN_TTL_SECONDS[FatigueSeverity.MEDIUM]

    def test_returns_none_after_clear(self, engine):
        engine.set_account_cooldown("acct-1", FatigueSeverity.LOW)
        engine.clear_account_cooldown("acct-1")
        assert engine.get_account_cooldown_info("acct-1") is None


# ---------------------------------------------------------------------------
# Member cooldowns — set / check / clear
# ---------------------------------------------------------------------------


class TestMemberCooldown:
    def test_not_on_cooldown_by_default(self, engine):
        assert engine.is_member_on_cooldown("mem-1") is False

    def test_set_cooldown_returns_ttl(self, engine):
        ttl = engine.set_member_cooldown("mem-1", FatigueSeverity.CRITICAL)
        assert ttl == COOLDOWN_TTL_SECONDS[FatigueSeverity.CRITICAL]

    def test_is_on_cooldown_after_set(self, engine):
        engine.set_member_cooldown("mem-1", FatigueSeverity.LOW)
        assert engine.is_member_on_cooldown("mem-1") is True

    def test_clear_removes_cooldown(self, engine):
        engine.set_member_cooldown("mem-1", FatigueSeverity.MEDIUM)
        engine.clear_member_cooldown("mem-1")
        assert engine.is_member_on_cooldown("mem-1") is False

    def test_clear_returns_true_when_was_set(self, engine):
        engine.set_member_cooldown("mem-1", FatigueSeverity.HIGH)
        assert engine.clear_member_cooldown("mem-1") is True

    def test_member_cooldown_independent_of_account(self, engine):
        engine.set_account_cooldown("acct-1", FatigueSeverity.HIGH)
        assert engine.is_member_on_cooldown("acct-1") is False

    def test_different_members_independent(self, engine):
        engine.set_member_cooldown("mem-1", FatigueSeverity.CRITICAL)
        assert engine.is_member_on_cooldown("mem-2") is False


# ---------------------------------------------------------------------------
# Member cooldowns — get_member_cooldown_info
# ---------------------------------------------------------------------------


class TestGetMemberCooldownInfo:
    def test_returns_none_when_not_set(self, engine):
        assert engine.get_member_cooldown_info("mem-x") is None

    def test_returns_entry_when_set(self, engine):
        engine.set_member_cooldown("mem-1", FatigueSeverity.CRITICAL)
        entry = engine.get_member_cooldown_info("mem-1")
        assert isinstance(entry, CooldownEntry)
        assert entry.entity_type == "member"
        assert entry.entity_id == "mem-1"
        assert entry.severity == FatigueSeverity.CRITICAL


# ---------------------------------------------------------------------------
# apply_fatigue_score — integration with AccountFatigueScore
# ---------------------------------------------------------------------------


class TestApplyFatigueScore:
    def _make_score(self, score_val: float, severity: FatigueSeverity):
        from scoring.models import AccountFatigueScore
        return AccountFatigueScore(
            account_id="acct-1",
            account_domain="acme.com",
            score=score_val,
            severity=severity,
        )

    def test_sets_cooldown_for_high_severity(self, engine):
        score = self._make_score(65.0, FatigueSeverity.HIGH)
        result = engine.apply_fatigue_score("acct-1", score)
        assert result["action"] == "set"
        assert result["ttl"] == COOLDOWN_TTL_SECONDS[FatigueSeverity.HIGH]
        assert engine.is_account_on_cooldown("acct-1") is True

    def test_sets_cooldown_for_critical_severity(self, engine):
        score = self._make_score(85.0, FatigueSeverity.CRITICAL)
        result = engine.apply_fatigue_score("acct-1", score)
        assert result["action"] == "set"
        assert engine.is_account_on_cooldown("acct-1") is True

    def test_clears_cooldown_when_severity_drops(self, engine):
        # First set a HIGH cooldown
        engine.set_account_cooldown("acct-1", FatigueSeverity.HIGH)
        # Now score has recovered to LOW
        score = self._make_score(20.0, FatigueSeverity.LOW)
        result = engine.apply_fatigue_score("acct-1", score)
        assert result["action"] == "cleared"
        assert engine.is_account_on_cooldown("acct-1") is False

    def test_no_change_when_below_threshold_and_not_set(self, engine):
        score = self._make_score(15.0, FatigueSeverity.LOW)
        result = engine.apply_fatigue_score("acct-1", score)
        assert result["action"] == "no_change"

    def test_no_change_for_medium_severity(self, engine):
        score = self._make_score(40.0, FatigueSeverity.MEDIUM)
        result = engine.apply_fatigue_score("acct-1", score)
        assert result["action"] == "no_change"
        assert engine.is_account_on_cooldown("acct-1") is False

    def test_raises_for_wrong_type(self, engine):
        with pytest.raises(TypeError):
            engine.apply_fatigue_score("acct-1", {"score": 80.0})


# ---------------------------------------------------------------------------
# Redis failure handling (fail-safe reads)
# ---------------------------------------------------------------------------


class TestRedisFailureHandling:
    def test_is_account_on_cooldown_returns_true_on_failure(self):
        class BrokenRedis:
            def get(self, key):
                raise ConnectionError("Redis down")

        engine = ActionCooldownEngine(BrokenRedis())
        # Fail-safe: assume cooldown is active
        assert engine.is_account_on_cooldown("acct-1") is True

    def test_is_member_on_cooldown_returns_true_on_failure(self):
        class BrokenRedis:
            def get(self, key):
                raise ConnectionError("Redis down")

        engine = ActionCooldownEngine(BrokenRedis())
        assert engine.is_member_on_cooldown("mem-1") is True

    def test_get_account_cooldown_info_returns_none_on_failure(self):
        class BrokenRedis:
            def get(self, key):
                raise ConnectionError("Redis down")

        engine = ActionCooldownEngine(BrokenRedis())
        assert engine.get_account_cooldown_info("acct-1") is None

    def test_set_cooldown_raises_on_failure(self):
        class BrokenRedis:
            def set(self, key, value, ex=None):
                raise ConnectionError("Redis down")

        engine = ActionCooldownEngine(BrokenRedis())
        with pytest.raises(ConnectionError):
            engine.set_account_cooldown("acct-1", FatigueSeverity.HIGH)


# ---------------------------------------------------------------------------
# Key format verification
# ---------------------------------------------------------------------------


class TestKeyFormat:
    def test_account_key_format(self):
        key = _account_key("some-uuid")
        assert key == "cooldown:account:some-uuid"

    def test_member_key_format(self):
        key = _member_key("member-uuid")
        assert key == "cooldown:member:member-uuid"

    def test_account_and_member_keys_dont_collide(self):
        assert _account_key("x") != _member_key("x")
