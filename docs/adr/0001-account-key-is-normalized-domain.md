# 0001: Account Key Is Normalized Email Domain
**Status**: Accepted
**Date**: 2026-05-17

## Context

harmoni tracks buying committees at the account level, not the individual contact level. A single target company generates signals from multiple stakeholders across multiple systems (CRM, email, web analytics, webinars). To unify these signals we need a stable, universal primary key that works across all source systems without requiring a shared ID scheme.

Options considered:
1. **CRM company ID** — system-specific, breaks for companies not yet in the CRM, incompatible across HubSpot/Salesforce/etc.
2. **Normalized email domain** — universally derivable from any contact record, stable across CRM migrations, no lookup required.
3. **UUID generated at first sight** — requires a central lookup before any signal can be attributed, adds latency and a single point of failure.

## Decision

The canonical `Account` key is the **normalized email domain**: the domain portion of a contact's email, lowercased, stripped of leading `www.`, and with free-email providers (gmail.com, yahoo.com, etc.) rejected at ingestion time.

The canonical normalization function is:

```python
def normalize_domain(email_or_domain: str) -> str:
    """Extract and lowercase the domain portion of an email or domain string."""
    domain = email_or_domain.split("@")[-1].strip().lower()
    return domain
```

All events, scores, actions, and API responses use this domain key as the primary account identifier. Secondary resolution strategies (IP-to-company, CRM cross-reference, domain alias tables) are layered on top in Sprint 3 but always resolve _to_ a canonical domain key.

## Consequences

- **Positive**: Zero infrastructure required to derive the key; works offline; consistent across all source systems.
- **Positive**: Domain normalization is idempotent — re-running produces the same key.
- **Negative**: Domain aliasing (corp.com → acquired-startup.io) requires an explicit alias table, managed in the identity resolution layer.
- **Negative**: Personal-email users (gmail, hotmail) cannot be attributed to an account; they are quarantined rather than silently dropped.
- **Constraint**: Every pipeline stage and API endpoint must normalize before lookup. The `normalize_domain()` function in `identity/resolver.py` is the single canonical implementation.
