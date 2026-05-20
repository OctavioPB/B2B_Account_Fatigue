"""Canonical Kafka topic definitions for the harmoni CEP pipeline.

Topic naming convention: harmoni.{source}.{event_type}
All topics are partitioned by account_domain for ordered, per-account processing.

Reference: ingestion/kafka/README.md
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TopicConfig:
    """Immutable topic configuration record."""

    name: str
    partitions: int
    replication_factor: int
    retention_ms: int  # -1 = infinite retention
    cleanup_policy: str = "delete"
    schema_subject: str = field(init=False)

    def __post_init__(self) -> None:
        # schema_subject follows Confluent TopicNameStrategy
        object.__setattr__(self, "schema_subject", f"{self.name}-value")

    def to_confluent_config(self) -> dict[str, str]:
        """Return topic config dict for confluent-kafka AdminClient."""
        cfg: dict[str, str] = {
            "cleanup.policy": self.cleanup_policy,
        }
        if self.retention_ms != -1:
            cfg["retention.ms"] = str(self.retention_ms)
        return cfg


_7_DAYS_MS = 7 * 24 * 60 * 60 * 1_000
_30_DAYS_MS = 30 * 24 * 60 * 60 * 1_000
_90_DAYS_MS = 90 * 24 * 60 * 60 * 1_000


# ---------------------------------------------------------------------------
# Canonical topic registry
# Order matters: DLQ is always registered/created first.
# ---------------------------------------------------------------------------

DLQ = TopicConfig(
    name="harmoni.dlq",
    partitions=3,
    replication_factor=1,
    retention_ms=_90_DAYS_MS,
)

WEB_PAGEVIEW = TopicConfig(
    name="harmoni.web.pageview",
    partitions=6,
    replication_factor=1,
    retention_ms=_30_DAYS_MS,
)

EMAIL_ENGAGEMENT = TopicConfig(
    name="harmoni.email.engagement",
    partitions=6,
    replication_factor=1,
    retention_ms=_30_DAYS_MS,
)

CRM_CONTACT_ACTIVITY = TopicConfig(
    name="harmoni.crm.contact_activity",
    partitions=6,
    replication_factor=1,
    retention_ms=_30_DAYS_MS,
)

WEBINAR_ATTENDANCE = TopicConfig(
    name="harmoni.webinar.attendance",
    partitions=6,
    replication_factor=1,
    retention_ms=_30_DAYS_MS,
)

# Registry: all topics in creation order (DLQ always first)
ALL_TOPICS: tuple[TopicConfig, ...] = (
    DLQ,
    WEB_PAGEVIEW,
    EMAIL_ENGAGEMENT,
    CRM_CONTACT_ACTIVITY,
    WEBINAR_ATTENDANCE,
)

# Map from topic name to config for O(1) lookups
TOPIC_BY_NAME: dict[str, TopicConfig] = {t.name: t for t in ALL_TOPICS}


def get_topic(name: str) -> TopicConfig:
    """Return TopicConfig by name; raises KeyError for unknown topics."""
    try:
        return TOPIC_BY_NAME[name]
    except KeyError:
        raise KeyError(f"Unknown topic: {name!r}. Valid topics: {list(TOPIC_BY_NAME)}")
