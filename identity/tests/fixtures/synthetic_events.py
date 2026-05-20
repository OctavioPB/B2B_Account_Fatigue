"""Synthetic event generator for identity resolution accuracy tests.

Generates a labelled dataset of ResolutionInput → expected_domain pairs
that covers all five resolution strategies defined in ADR 0005:

    1. explicit_domain  → HIGH (10 samples)
    2. email_domain     → HIGH (30 samples)
    3. alias_table      → HIGH (10 samples)
    4. crm_xref         → MEDIUM (15 samples)
    5. ip_enrichment    → MEDIUM/LOW (15 samples)

Plus edge cases that must route to quarantine:
    - free email domains (10 samples)
    - invalid domains    (5 samples)
    - anonymous IP only  (5 samples, LOW confidence)

Total: 100 synthetic labelled events.

Usage::

    events, stub_aliases, stub_crm, stub_ip = make_synthetic_dataset()

Returns:
    events: list of (ResolutionInput, expected_domain: str | None) tuples.
    stub_aliases: dict[alias_domain → canonical_domain] for mocking get_alias().
    stub_crm:     dict[(crm_source, crm_company_id) → canonical_domain].
    stub_ip:      dict[ip_address → (domain, confidence)] for mocking enrich_by_ip().
"""

from __future__ import annotations

from typing import NamedTuple

from identity.models import ResolutionInput


class SyntheticEvent(NamedTuple):
    signal: ResolutionInput
    expected_domain: str | None  # None = should quarantine
    expected_high_confidence: bool  # True if result should be HIGH


# ---------------------------------------------------------------------------
# Base data pools
# ---------------------------------------------------------------------------

_BUSINESS_DOMAINS = [
    "acme.com", "globex.com", "initech.com", "umbrella.com", "cyberdyne.com",
    "soylent.com", "tyrell.com", "weyland.com", "veridian.com", "oscorp.com",
    "stark.io", "wayne.com", "queen.com", "parker.io", "barton.biz",
    "rogers.com", "banner.io", "lang.co", "pym.tech", "maximoff.com",
    "vision.ai", "rhodes.io", "fury.gov", "hill.com", "foster.edu",
    "darcy.co.uk", "coulson.io", "may.com", "happy.biz", "pepper.com",
]

_FREE_EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "protonmail.com", "aol.com", "zoho.com", "gmx.com", "fastmail.com",
]

_ALIAS_MAP: dict[str, str] = {
    "old-acme.com": "acme.com",
    "acme-corp.io": "acme.com",
    "globex-inc.com": "globex.com",
    "initech-legacy.com": "initech.com",
    "umbrella-pharma.com": "umbrella.com",
    "cyberdyne-robotics.com": "cyberdyne.com",
    "soylent-green.io": "soylent.com",
    "tyrell-corp.io": "tyrell.com",
    "weyland-yutani.com": "weyland.com",
    "veridian-dynamics.biz": "veridian.com",
}

_CRM_MAP: dict[tuple[str, str], str] = {
    ("HUBSPOT", "hs-001"): "stark.io",
    ("HUBSPOT", "hs-002"): "wayne.com",
    ("HUBSPOT", "hs-003"): "queen.com",
    ("SALESFORCE", "sf-001"): "parker.io",
    ("SALESFORCE", "sf-002"): "barton.biz",
    ("SALESFORCE", "sf-003"): "rogers.com",
    ("PIPEDRIVE", "pd-001"): "banner.io",
    ("PIPEDRIVE", "pd-002"): "lang.co",
    ("HUBSPOT", "hs-004"): "pym.tech",
    ("HUBSPOT", "hs-005"): "maximoff.com",
    ("SALESFORCE", "sf-004"): "vision.ai",
    ("SALESFORCE", "sf-005"): "rhodes.io",
    ("PIPEDRIVE", "pd-003"): "fury.gov",
    ("HUBSPOT", "hs-006"): "hill.com",
    ("SALESFORCE", "sf-006"): "foster.edu",
}

_IP_MAP: dict[str, tuple[str, float]] = {
    "10.0.0.1": ("darcy.co.uk", 0.92),
    "10.0.0.2": ("coulson.io", 0.88),
    "10.0.0.3": ("may.com", 0.85),
    "10.0.0.4": ("happy.biz", 0.80),
    "10.0.0.5": ("pepper.com", 0.75),
    # Low confidence — should still resolve but route to LOW tier
    "10.1.0.1": ("low-confidence-a.com", 0.55),
    "10.1.0.2": ("low-confidence-b.com", 0.50),
    "10.1.0.3": ("low-confidence-c.com", 0.45),
    "10.1.0.4": ("low-confidence-d.com", 0.40),
    "10.1.0.5": ("low-confidence-e.com", 0.35),
    # Anonymous — no company resolution available
    "10.2.0.1": (None, 0.0),
    "10.2.0.2": (None, 0.0),
    "10.2.0.3": (None, 0.0),
    "10.2.0.4": (None, 0.0),
    "10.2.0.5": (None, 0.0),
}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def make_synthetic_dataset() -> tuple[
    list[SyntheticEvent],
    dict[str, str],
    dict[tuple[str, str], str],
    dict[str, tuple[str | None, float]],
]:
    """Build the full labelled test dataset.

    Returns:
        (events, stub_aliases, stub_crm, stub_ip)
    """
    events: list[SyntheticEvent] = []

    # ---- Strategy 1: explicit_domain (10 events) ----
    for domain in _BUSINESS_DOMAINS[:10]:
        events.append(SyntheticEvent(
            signal=ResolutionInput(
                explicit_domain=domain,
                source_event_id=f"exp-{domain}",
                source_topic="harmoni.crm.contact_activity",
            ),
            expected_domain=domain,
            expected_high_confidence=True,
        ))

    # ---- Strategy 2: email_domain (30 events, business emails) ----
    for domain in _BUSINESS_DOMAINS:
        events.append(SyntheticEvent(
            signal=ResolutionInput(
                email=f"user@{domain}",
                source_event_id=f"email-{domain}",
                source_topic="harmoni.email.engagement",
            ),
            expected_domain=domain,
            expected_high_confidence=True,
        ))

    # ---- Strategy 2b: alias table (10 events) ----
    for alias_domain, canonical in _ALIAS_MAP.items():
        events.append(SyntheticEvent(
            signal=ResolutionInput(
                email=f"contact@{alias_domain}",
                source_event_id=f"alias-{alias_domain}",
                source_topic="harmoni.email.engagement",
            ),
            expected_domain=canonical,
            expected_high_confidence=True,
        ))

    # ---- Strategy 3: CRM company-ID (15 events) ----
    for (crm_source, crm_id), domain in _CRM_MAP.items():
        events.append(SyntheticEvent(
            signal=ResolutionInput(
                email=f"contact@gmail.com",  # free email → falls through to CRM
                crm_company_id=crm_id,
                crm_source=crm_source,
                source_event_id=f"crm-{crm_id}",
                source_topic="harmoni.crm.contact_activity",
            ),
            expected_domain=domain,
            expected_high_confidence=False,  # MEDIUM
        ))

    # ---- Strategy 4: IP enrichment — HIGH/MEDIUM confidence (5 events) ----
    for ip, (domain, _conf) in list(_IP_MAP.items())[:5]:
        events.append(SyntheticEvent(
            signal=ResolutionInput(
                ip_address=ip,
                source_event_id=f"ip-{ip}",
                source_topic="harmoni.web.pageview",
            ),
            expected_domain=domain,
            expected_high_confidence=False,  # MEDIUM
        ))

    # ---- Strategy 4b: IP enrichment — LOW confidence (5 events, should quarantine) ----
    for ip, (domain, _conf) in list(_IP_MAP.items())[5:10]:
        events.append(SyntheticEvent(
            signal=ResolutionInput(
                ip_address=ip,
                source_event_id=f"ip-low-{ip}",
                source_topic="harmoni.web.pageview",
            ),
            expected_domain=domain,  # domain exists but confidence is LOW
            expected_high_confidence=False,
        ))

    # ---- Free email + no fallback → quarantine (10 events) ----
    for free_domain in _FREE_EMAIL_DOMAINS:
        events.append(SyntheticEvent(
            signal=ResolutionInput(
                email=f"user@{free_domain}",
                source_event_id=f"free-{free_domain}",
                source_topic="harmoni.email.engagement",
            ),
            expected_domain=None,  # quarantine
            expected_high_confidence=False,
        ))

    # ---- Invalid domain → quarantine (5 events) ----
    for invalid in ["-invalid.com", "no_tld", "a" * 300, "test@", "double..dot.com"]:
        events.append(SyntheticEvent(
            signal=ResolutionInput(
                email=f"{invalid}",
                source_event_id=f"invalid-{len(events)}",
                source_topic="harmoni.email.engagement",
            ),
            expected_domain=None,
            expected_high_confidence=False,
        ))

    # ---- Anonymous IP with no company resolution → quarantine (5 events) ----
    for ip, (_domain, _conf) in list(_IP_MAP.items())[10:15]:
        events.append(SyntheticEvent(
            signal=ResolutionInput(
                ip_address=ip,
                source_event_id=f"anon-{ip}",
                source_topic="harmoni.web.pageview",
            ),
            expected_domain=None,
            expected_high_confidence=False,
        ))

    return events, _ALIAS_MAP.copy(), dict(_CRM_MAP), dict(_IP_MAP)
