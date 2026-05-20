"""Smoke tests — assert liveness for every service in docker-compose.yml.

Each test connects to a service and verifies a minimal health assertion.
Tests are marked @pytest.mark.smoke and @pytest.mark.integration so they can
be excluded from the fast unit-test run.

Run: pytest -m smoke -v
"""

import asyncio
import pytest


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.integration
def test_postgres_liveness(database_url: str) -> None:
    """Connects to PostgreSQL and asserts SELECT 1 returns 1."""
    import asyncpg

    async def _check() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            result = await conn.fetchval("SELECT 1")
            assert result == 1, f"Expected 1, got {result}"
        finally:
            await conn.close()

    asyncio.run(_check())


# ---------------------------------------------------------------------------
# ClickHouse
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.integration
def test_clickhouse_liveness(clickhouse_host: str, clickhouse_port: int) -> None:
    """Connects to ClickHouse native TCP interface and asserts SELECT 1."""
    from clickhouse_driver import Client  # type: ignore[import]

    client = Client(host=clickhouse_host, port=clickhouse_port)
    result = client.execute("SELECT 1")
    assert result == [(1,)], f"Unexpected result: {result}"


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.integration
def test_redis_liveness(redis_url: str) -> None:
    """Connects to Redis and asserts PING returns PONG."""
    import redis as redis_client

    r = redis_client.from_url(redis_url)
    assert r.ping(), "Redis PING failed"
    r.close()


# ---------------------------------------------------------------------------
# Kafka
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.integration
def test_kafka_liveness(kafka_bootstrap_servers: str) -> None:
    """Connects to Kafka and lists topics (at minimum zero topics expected)."""
    from confluent_kafka.admin import AdminClient  # type: ignore[import]

    admin = AdminClient({"bootstrap.servers": kafka_bootstrap_servers})
    metadata = admin.list_topics(timeout=10)
    # Cluster is reachable if we can list topics without exception
    assert metadata is not None, "Kafka metadata call returned None"


# ---------------------------------------------------------------------------
# Schema Registry
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.integration
def test_schema_registry_liveness(schema_registry_url: str) -> None:
    """Hits the Schema Registry /subjects endpoint and asserts HTTP 200."""
    import urllib.request

    url = f"{schema_registry_url}/subjects"
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        assert resp.status == 200, f"Schema Registry returned {resp.status}"


# ---------------------------------------------------------------------------
# Airflow
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.integration
def test_airflow_liveness(airflow_url: str) -> None:
    """Hits the Airflow /health endpoint and asserts HTTP 200."""
    import urllib.request

    url = f"{airflow_url}/health"
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
        assert resp.status == 200, f"Airflow returned {resp.status}"
