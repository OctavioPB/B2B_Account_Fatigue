# 0005: Account Resolution Confidence Tiers
**Status**: Accepted
**Date**: 2026-05-17

## Context

Events arrive in the harmoni pipeline from sources (web, email, CRM, webinar) where
account attribution is ambiguous. A web pixel event may carry only an IP address;
a CRM event may carry a contact email from a personal address; a webinar registration
may carry a company name but not a domain. Silently dropping unattributed events
causes undercount of intent signals and inaccurate fatigue scores.

The system needs a principled way to:
1. Indicate how confident we are in a resolved `Account`
2. Decide what to do with signals we can't fully attribute
3. Make the resolution audit trail inspectable

Four approaches considered:
1. **Binary (resolved / dropped)** — simple but loses LOW-confidence signals that could be manually recovered.
2. **Four-tier confidence (HIGH / MEDIUM / LOW / UNRESOLVABLE)** — preserves signals at every tier; routes them appropriately.
3. **Probability score (0.0–1.0)** — continuous but adds ML complexity before it's warranted.
4. **Source-based trust levels** — conflates resolution confidence with source reliability.

## Decision

Adopt a **four-tier confidence system** with the following semantics and routing rules:

| Tier | Meaning | Routing |
|---|---|---|
| `HIGH` | Direct business email domain match or active alias table entry | Proceed to scoring |
| `MEDIUM` | IP-to-company enrichment (high-confidence provider) or CRM company-ID cross-reference | Proceed to scoring with confidence flag on IntentSignal |
| `LOW` | IP-to-company with low enrichment confidence, or ambiguous CRM partial match | **Quarantine** for manual review |
| `UNRESOLVABLE` | Free email domain, anonymous event with no resolution vector, invalid domain | **Quarantine** — never silently drop |

### Resolution Strategy Waterfall

The `AsyncAccountResolver` tries strategies in priority order, stopping at the first
result with `HIGH` or `MEDIUM` confidence:

```
1. explicit_domain       → always HIGH (caller-supplied, trusted)
2. email domain lookup   → HIGH if business domain, UNRESOLVABLE if free email
3. domain alias table    → HIGH if active alias exists
4. CRM company-ID xref  → MEDIUM
5. IP-to-company API     → MEDIUM (confidence >= 0.7) or LOW (< 0.7)
6. → UNRESOLVABLE
```

### Quarantine Behavior

`LOW` and `UNRESOLVABLE` events are written to `resolution_quarantine` with:
- Full raw event payload (for manual inspection)
- `resolution_attempt` JSON (which strategies were tried, what was found)
- `status = PENDING`

Operations can resolve quarantined events by supplying the correct `canonical_domain`,
which triggers re-processing. Events that cannot be recovered are marked `DISCARDED`
(not deleted — preserve for audit).

## Consequences

- **Positive**: No signal is ever silently dropped; every unresolved event is inspectable and recoverable.
- **Positive**: `MEDIUM`-confidence signals still flow to the scoring engine, labelled with their tier, allowing the `IntentNetworkModel` (Sprint 5) to apply a confidence discount.
- **Positive**: The quarantine volume is an operational health metric — rising quarantine rate indicates a resolution pipeline problem or a new signal source requiring an alias entry.
- **Negative**: Quarantine table can grow large for high-volume anonymous web traffic. Mitigation: add IP-to-company enrichment early in the pipeline to convert anonymous events to `MEDIUM` confidence before they reach quarantine.
- **Operational**: Monitor `SELECT status, COUNT(*) FROM resolution_quarantine GROUP BY status` daily. Alert if PENDING count exceeds 1,000.
