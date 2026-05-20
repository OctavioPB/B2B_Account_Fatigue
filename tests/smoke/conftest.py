"""Smoke test configuration.

Smoke tests require all Docker services to be running. Run via:
    pytest -m smoke

Skip smoke tests in unit-only CI runs:
    pytest -m "not smoke"
"""

import os
import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "smoke: liveness checks — requires Docker services (docker-compose up -d)",
    )


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://harmoni:harmoni@localhost:5432/harmoni")


@pytest.fixture(scope="session")
def redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(scope="session")
def clickhouse_host() -> str:
    return os.environ.get("CLICKHOUSE_HOST", "localhost")


@pytest.fixture(scope="session")
def clickhouse_port() -> int:
    return int(os.environ.get("CLICKHOUSE_PORT", "9000"))


@pytest.fixture(scope="session")
def kafka_bootstrap_servers() -> str:
    return os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


@pytest.fixture(scope="session")
def schema_registry_url() -> str:
    return os.environ.get("KAFKA_SCHEMA_REGISTRY_URL", "http://localhost:8081")


@pytest.fixture(scope="session")
def airflow_url() -> str:
    return "http://localhost:8082"
