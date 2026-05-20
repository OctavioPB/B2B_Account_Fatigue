"""Tests for orchestrator.rules.engine — NBAOrchestrator decision tree.

Coverage requirements (per Sprint 7 DoD):
  - Every ActionType has at least one test case.
  - Edge cases at each rule boundary are tested.
  - Conflict resolution (should_overwrite) tested for all protected/non-protected combos.
  - RL feature flag guard tested.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.models import (
    ACTION_PRIORITY,
    ActionType,
    NextBestAction,
    PROTECTED_ACTION_TYPES,
    should_overwrite,
)
from orchestrator.rules.engine import NBAOrchestrator, _apply_rules
from scoring.models import (
    AccountFatigueScore,
    ChurnPrediction,
    ChurnRiskLevel,
    FatigueSeverity,
    IntentScore,
)

_NOW = datetime(2024, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Signal builders
# ---------------------------------------------------------------------------


def _fatigue(severity: FatigueSeverity, score: float = 50.0) -> AccountFatigueScore:
    score_map = {
        FatigueSeverity.LOW: 15.0,
        FatigueSeverity.MEDIUM: 45.0,
        FatigueSeverity.HIGH: 70.0,
        FatigueSeverity.CRITICAL: 90.0,
    }
    return AccountFatigueScore(
        account_id="acct-1",
        account_domain="test.com",
        score=score_map[severity],
        severity=severity,
    )


def _intent(score: float) -> IntentScore:
    return IntentScore(
        account_id="acct-1",
        account_domain="test.com",
        score=score,
        confidence=0.8,
    )


def _churn(risk_level: ChurnRiskLevel, prob: float | None = None) -> ChurnPrediction:
    prob_map = {
        ChurnRiskLevel.LOW:      0.10,
        ChurnRiskLevel.MEDIUM:   0.35,
        ChurnRiskLevel.HIGH:     0.62,
        ChurnRiskLevel.CRITICAL: 0.85,
    }
    return ChurnPrediction(
        account_id="acct-1",
        account_domain="test.com",
        churn_probability=prob if prob is not None else prob_map[risk_level],
        risk_level=risk_level,
    )


def _orchestrator() -> NBAOrchestrator:
    """Return an NBAOrchestrator with the RL flag explicitly OFF."""
    os.environ.pop("FEATURE_RL_ORCHESTRATOR", None)
    return NBAOrchestrator()


# ===========================================================================
# Action type taxonomy — all 7 types covered
# ===========================================================================


class TestAllActionTypesCovered:
    """Every ActionType must be reachable by some combination of signals."""

    def test_cooldown_triggered_by_high_fatigue(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.HIGH),
            _intent(80.0),
            _churn(ChurnRiskLevel.LOW),
        )
        assert action == ActionType.COOLDOWN

    def test_cooldown_triggered_by_critical_fatigue(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.CRITICAL),
            _intent(85.0),
            _churn(ChurnRiskLevel.LOW),
        )
        assert action == ActionType.COOLDOWN

    def test_deal_review_triggered_by_critical_churn(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(40.0),
            _churn(ChurnRiskLevel.CRITICAL),
        )
        assert action == ActionType.DEAL_REVIEW

    def test_exec_escalation_triggered_by_high_churn(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(50.0),
            _churn(ChurnRiskLevel.HIGH),
        )
        assert action == ActionType.EXEC_ESCALATION

    def test_accelerate_triggered_by_all_positive(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(75.0),
            _churn(ChurnRiskLevel.LOW),
        )
        assert action == ActionType.ACCELERATE

    def test_pricing_trigger_triggered_by_high_intent_medium_conditions(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.MEDIUM),
            _intent(72.0),
            _churn(ChurnRiskLevel.MEDIUM),
        )
        assert action == ActionType.PRICING_TRIGGER

    def test_re_engage_triggered_by_medium_churn_low_intent(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(40.0),
            _churn(ChurnRiskLevel.MEDIUM),
        )
        assert action == ActionType.RE_ENGAGE

    def test_nurture_is_default_for_low_signals(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(30.0),
            _churn(ChurnRiskLevel.LOW),
        )
        assert action == ActionType.NURTURE


# ===========================================================================
# Decision tree — rule priority order
# ===========================================================================


class TestRulePriority:
    """Fatigue override (Rule 1) must beat every other signal."""

    def test_cooldown_beats_critical_churn(self):
        # Even if churn is CRITICAL, HIGH fatigue wins
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.HIGH),
            _intent(20.0),
            _churn(ChurnRiskLevel.CRITICAL),
        )
        assert action == ActionType.COOLDOWN

    def test_cooldown_beats_high_intent(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.CRITICAL),
            _intent(95.0),
            _churn(ChurnRiskLevel.LOW),
        )
        assert action == ActionType.COOLDOWN

    def test_deal_review_beats_exec_escalation(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(60.0),
            _churn(ChurnRiskLevel.CRITICAL),
        )
        assert action == ActionType.DEAL_REVIEW

    def test_exec_escalation_beats_pricing_trigger(self):
        # High churn + high intent → EXEC_ESCALATION not PRICING_TRIGGER
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(80.0),
            _churn(ChurnRiskLevel.HIGH),
        )
        assert action == ActionType.EXEC_ESCALATION

    def test_accelerate_beats_pricing_trigger_when_all_low(self):
        # Intent ≥ 70, fatigue LOW, churn LOW → ACCELERATE (Rule 4) before PRICING_TRIGGER (Rule 5)
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(70.0),
            _churn(ChurnRiskLevel.LOW),
        )
        assert action == ActionType.ACCELERATE

    def test_pricing_trigger_when_churn_medium(self):
        # Intent ≥ 70 but churn MEDIUM → cannot ACCELERATE → PRICING_TRIGGER
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(75.0),
            _churn(ChurnRiskLevel.MEDIUM),
        )
        assert action == ActionType.PRICING_TRIGGER

    def test_re_engage_before_nurture(self):
        # Medium churn, low intent → RE_ENGAGE not NURTURE
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.MEDIUM),
            _intent(20.0),
            _churn(ChurnRiskLevel.MEDIUM),
        )
        assert action == ActionType.RE_ENGAGE


# ===========================================================================
# Decision tree — boundary conditions
# ===========================================================================


class TestBoundaryConditions:
    def test_intent_exactly_at_high_threshold(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(70.0),  # exactly at threshold
            _churn(ChurnRiskLevel.LOW),
        )
        assert action == ActionType.ACCELERATE

    def test_intent_just_below_high_threshold(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(69.9),
            _churn(ChurnRiskLevel.LOW),
        )
        # Not ACCELERATE or PRICING_TRIGGER — falls through to NURTURE
        assert action == ActionType.NURTURE

    def test_fatigue_medium_does_not_trigger_cooldown(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.MEDIUM),
            _intent(30.0),
            _churn(ChurnRiskLevel.LOW),
        )
        assert action != ActionType.COOLDOWN

    def test_churn_low_does_not_trigger_deal_review(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(30.0),
            _churn(ChurnRiskLevel.LOW),
        )
        assert action not in (ActionType.DEAL_REVIEW, ActionType.EXEC_ESCALATION)

    def test_zero_intent_low_churn_low_fatigue_gives_nurture(self):
        action, _, _ = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(0.0),
            _churn(ChurnRiskLevel.LOW),
        )
        assert action == ActionType.NURTURE


# ===========================================================================
# Triggered_by and rationale
# ===========================================================================


class TestTriggeredByAndRationale:
    def test_cooldown_triggered_by_contains_fatigue(self):
        _, _, triggered = _apply_rules(
            _fatigue(FatigueSeverity.CRITICAL),
            _intent(50.0),
            _churn(ChurnRiskLevel.LOW),
        )
        assert any("fatigue" in t.lower() for t in triggered)

    def test_deal_review_triggered_by_contains_churn(self):
        _, _, triggered = _apply_rules(
            _fatigue(FatigueSeverity.LOW),
            _intent(50.0),
            _churn(ChurnRiskLevel.CRITICAL),
        )
        assert any("churn" in t.lower() for t in triggered)

    def test_rationale_is_nonempty(self):
        for sev in FatigueSeverity:
            for churn_lv in ChurnRiskLevel:
                _, rationale, _ = _apply_rules(
                    _fatigue(sev),
                    _intent(50.0),
                    _churn(churn_lv),
                )
                assert rationale, f"Empty rationale for sev={sev} churn={churn_lv}"


# ===========================================================================
# NBAOrchestrator.decide — output contract
# ===========================================================================


class TestNBAOrchestratorDecide:
    def setup_method(self):
        self.orch = _orchestrator()

    def test_returns_next_best_action(self):
        action = self.orch.decide(
            "acct-1", "acme.com",
            _fatigue(FatigueSeverity.LOW),
            _intent(50.0),
            _churn(ChurnRiskLevel.LOW),
            as_of=_NOW,
        )
        assert isinstance(action, NextBestAction)

    def test_account_id_and_domain_propagated(self):
        action = self.orch.decide(
            "my-account", "my-domain.com",
            _fatigue(FatigueSeverity.LOW),
            _intent(50.0),
            _churn(ChurnRiskLevel.LOW),
            as_of=_NOW,
        )
        assert action.account_id == "my-account"
        assert action.account_domain == "my-domain.com"

    def test_score_snapshots_populated(self):
        action = self.orch.decide(
            "a", "b.com",
            _fatigue(FatigueSeverity.LOW),
            _intent(55.0),
            _churn(ChurnRiskLevel.LOW, prob=0.12),
            as_of=_NOW,
        )
        assert action.fatigue_score is not None
        assert action.intent_score == pytest.approx(55.0, abs=0.1)
        assert action.churn_probability == pytest.approx(0.12, abs=0.001)

    def test_priority_matches_action_type(self):
        action = self.orch.decide(
            "a", "b.com",
            _fatigue(FatigueSeverity.HIGH),
            _intent(50.0),
            _churn(ChurnRiskLevel.LOW),
            as_of=_NOW,
        )
        assert action.priority == ACTION_PRIORITY[ActionType.COOLDOWN]

    def test_expires_at_is_future(self):
        action = self.orch.decide(
            "a", "b.com",
            _fatigue(FatigueSeverity.LOW),
            _intent(50.0),
            _churn(ChurnRiskLevel.LOW),
            as_of=_NOW,
        )
        assert action.expires_at > _NOW

    def test_cooldown_expires_7_days_out(self):
        action = self.orch.decide(
            "a", "b.com",
            _fatigue(FatigueSeverity.HIGH),
            _intent(50.0),
            _churn(ChurnRiskLevel.LOW),
            as_of=_NOW,
        )
        assert action.action_type == ActionType.COOLDOWN
        delta = action.expires_at - _NOW
        assert delta == timedelta(hours=168)

    def test_is_active_defaults_true(self):
        action = self.orch.decide(
            "a", "b.com",
            _fatigue(FatigueSeverity.LOW),
            _intent(50.0),
            _churn(ChurnRiskLevel.LOW),
            as_of=_NOW,
        )
        assert action.is_active is True


# ===========================================================================
# NBAOrchestrator.resolve — conflict resolution
# ===========================================================================


class TestConflictResolution:
    def setup_method(self):
        self.orch = _orchestrator()

    def _make_action(self, action_type: ActionType, is_active: bool = True) -> NextBestAction:
        return NextBestAction(
            account_id="a",
            account_domain="b.com",
            action_type=action_type,
            rationale="test",
            is_active=is_active,
            created_at=_NOW,
        )

    def test_no_existing_returns_incoming(self):
        incoming = self._make_action(ActionType.NURTURE)
        result = self.orch.resolve(None, incoming)
        assert result is incoming

    def test_inactive_existing_returns_incoming(self):
        existing = self._make_action(ActionType.COOLDOWN, is_active=False)
        incoming = self._make_action(ActionType.NURTURE)
        result = self.orch.resolve(existing, incoming)
        assert result is incoming

    def test_nurture_overwrites_nurture(self):
        existing = self._make_action(ActionType.NURTURE)
        incoming = self._make_action(ActionType.NURTURE)
        result = self.orch.resolve(existing, incoming)
        assert result is incoming

    def test_higher_priority_overwrites_lower(self):
        existing = self._make_action(ActionType.NURTURE)
        incoming = self._make_action(ActionType.DEAL_REVIEW)
        result = self.orch.resolve(existing, incoming)
        assert result is incoming

    # PROTECTED: COOLDOWN / DEAL_REVIEW are not overwritten by lower-priority actions

    def test_cooldown_not_overwritten_by_nurture(self):
        existing = self._make_action(ActionType.COOLDOWN)
        incoming = self._make_action(ActionType.NURTURE)
        result = self.orch.resolve(existing, incoming)
        assert result is existing

    def test_cooldown_not_overwritten_by_re_engage(self):
        existing = self._make_action(ActionType.COOLDOWN)
        incoming = self._make_action(ActionType.RE_ENGAGE)
        result = self.orch.resolve(existing, incoming)
        assert result is existing

    def test_deal_review_not_overwritten_by_exec_escalation(self):
        existing = self._make_action(ActionType.DEAL_REVIEW)
        incoming = self._make_action(ActionType.EXEC_ESCALATION)
        result = self.orch.resolve(existing, incoming)
        assert result is existing

    def test_cooldown_overwritten_by_cooldown(self):
        existing = self._make_action(ActionType.COOLDOWN)
        incoming = self._make_action(ActionType.COOLDOWN)
        result = self.orch.resolve(existing, incoming)
        assert result is incoming

    def test_deal_review_overwritten_by_cooldown(self):
        # COOLDOWN priority (1) < DEAL_REVIEW priority (2) → COOLDOWN wins
        existing = self._make_action(ActionType.DEAL_REVIEW)
        incoming = self._make_action(ActionType.COOLDOWN)
        result = self.orch.resolve(existing, incoming)
        assert result is incoming

    def test_all_non_protected_types_are_overwriteable(self):
        non_protected = [at for at in ActionType if at not in PROTECTED_ACTION_TYPES]
        nurture = self._make_action(ActionType.NURTURE)
        for action_type in non_protected:
            existing = self._make_action(action_type)
            result = self.orch.resolve(existing, nurture)
            assert result is nurture, f"{action_type} should be overwriteable by NURTURE"


# ===========================================================================
# should_overwrite helper
# ===========================================================================


class TestShouldOverwrite:
    def _action(self, at: ActionType, active: bool = True) -> NextBestAction:
        return NextBestAction(
            account_id="a", account_domain="b.com",
            action_type=at, rationale="x", is_active=active,
        )

    def test_inactive_existing_always_overwritten(self):
        for at in ActionType:
            assert should_overwrite(self._action(at, active=False), self._action(ActionType.NURTURE))

    @pytest.mark.parametrize("protected", list(PROTECTED_ACTION_TYPES))
    def test_protected_not_overwritten_by_lower_priority(self, protected):
        existing = self._action(protected)
        for at in ActionType:
            if ACTION_PRIORITY[at] > ACTION_PRIORITY[protected]:
                assert not should_overwrite(existing, self._action(at)), (
                    f"{protected} should not be overwritten by {at}"
                )


# ===========================================================================
# RL feature flag guard
# ===========================================================================


class TestRLFeatureFlagGuard:
    def test_orchestrator_instantiates_when_flag_off(self):
        os.environ.pop("FEATURE_RL_ORCHESTRATOR", None)
        orchestrator = NBAOrchestrator()  # must not raise
        assert orchestrator is not None

    def test_orchestrator_raises_when_flag_on(self):
        os.environ["FEATURE_RL_ORCHESTRATOR"] = "true"
        try:
            with pytest.raises(RuntimeError, match="FEATURE_RL_ORCHESTRATOR"):
                NBAOrchestrator()
        finally:
            os.environ.pop("FEATURE_RL_ORCHESTRATOR", None)

    def test_rl_module_raises_on_import_when_flag_off(self):
        os.environ.pop("FEATURE_RL_ORCHESTRATOR", None)
        import importlib
        import sys
        # Remove cached module if present
        for key in list(sys.modules):
            if "orchestrator.rl" in key:
                del sys.modules[key]
        with pytest.raises(ImportError, match="FEATURE_RL_ORCHESTRATOR"):
            import orchestrator.rl  # noqa: F401


# ===========================================================================
# NextBestAction helpers
# ===========================================================================


class TestNextBestActionHelpers:
    def _make(self, at: ActionType) -> NextBestAction:
        return NextBestAction(
            account_id="a", account_domain="b.com",
            action_type=at, rationale="test", created_at=_NOW,
        )

    def test_priority_matches_action_priority_map(self):
        for at in ActionType:
            assert self._make(at).priority == ACTION_PRIORITY[at]

    def test_is_protected_true_for_cooldown_and_deal_review(self):
        assert self._make(ActionType.COOLDOWN).is_protected is True
        assert self._make(ActionType.DEAL_REVIEW).is_protected is True

    def test_is_protected_false_for_others(self):
        for at in ActionType:
            if at not in PROTECTED_ACTION_TYPES:
                assert self._make(at).is_protected is False

    def test_to_dict_contains_required_keys(self):
        d = self._make(ActionType.NURTURE).to_dict()
        for key in ("account_id", "account_domain", "action_type", "priority",
                    "rationale", "triggered_by", "expires_at", "created_at", "is_active"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_action_type_is_string_value(self):
        d = self._make(ActionType.ACCELERATE).to_dict()
        assert d["action_type"] == "ACCELERATE"
