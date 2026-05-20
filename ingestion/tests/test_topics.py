"""Unit tests for topic configuration and admin utilities."""

from __future__ import annotations

import pytest

from ingestion.kafka.topics import (
    ALL_TOPICS,
    DLQ,
    CRM_CONTACT_ACTIVITY,
    EMAIL_ENGAGEMENT,
    WEBINAR_ATTENDANCE,
    WEB_PAGEVIEW,
    TOPIC_BY_NAME,
    get_topic,
)


@pytest.mark.unit
def test_dlq_is_first_topic() -> None:
    """DLQ must be registered/created first per ADR 0003."""
    assert ALL_TOPICS[0] is DLQ


@pytest.mark.unit
def test_all_topic_names_follow_convention() -> None:
    for t in ALL_TOPICS:
        assert t.name.startswith("harmoni."), f"{t.name} must start with 'harmoni.'"


@pytest.mark.unit
def test_schema_subjects_follow_topic_name_strategy() -> None:
    for t in ALL_TOPICS:
        assert t.schema_subject == f"{t.name}-value"


@pytest.mark.unit
def test_topic_by_name_contains_all_topics() -> None:
    assert len(TOPIC_BY_NAME) == len(ALL_TOPICS)
    for t in ALL_TOPICS:
        assert t.name in TOPIC_BY_NAME


@pytest.mark.unit
def test_get_topic_returns_correct_config() -> None:
    assert get_topic("harmoni.web.pageview") is WEB_PAGEVIEW
    assert get_topic("harmoni.email.engagement") is EMAIL_ENGAGEMENT
    assert get_topic("harmoni.crm.contact_activity") is CRM_CONTACT_ACTIVITY
    assert get_topic("harmoni.webinar.attendance") is WEBINAR_ATTENDANCE
    assert get_topic("harmoni.dlq") is DLQ


@pytest.mark.unit
def test_get_topic_raises_for_unknown() -> None:
    with pytest.raises(KeyError, match="Unknown topic"):
        get_topic("harmoni.nonexistent.topic")


@pytest.mark.unit
def test_all_data_topics_have_6_partitions() -> None:
    data_topics = [WEB_PAGEVIEW, EMAIL_ENGAGEMENT, CRM_CONTACT_ACTIVITY, WEBINAR_ATTENDANCE]
    for t in data_topics:
        assert t.partitions == 6, f"{t.name} should have 6 partitions"


@pytest.mark.unit
def test_dlq_has_longer_retention_than_data_topics() -> None:
    data_retention = WEB_PAGEVIEW.retention_ms
    assert DLQ.retention_ms > data_retention


@pytest.mark.unit
def test_confluent_config_includes_retention_ms() -> None:
    cfg = WEB_PAGEVIEW.to_confluent_config()
    assert "retention.ms" in cfg
    assert cfg["retention.ms"] == str(WEB_PAGEVIEW.retention_ms)


@pytest.mark.unit
def test_infinite_retention_topic_excludes_retention_ms_key() -> None:
    from ingestion.kafka.topics import TopicConfig
    infinite = TopicConfig(
        name="harmoni.test",
        partitions=1,
        replication_factor=1,
        retention_ms=-1,
    )
    cfg = infinite.to_confluent_config()
    assert "retention.ms" not in cfg
