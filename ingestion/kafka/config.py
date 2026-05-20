"""Kafka connection configuration, loaded from environment via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaConfig(BaseSettings):
    """Kafka and Schema Registry connection settings.

    All values are loaded from environment variables. See .env.example.
    """

    model_config = SettingsConfigDict(
        env_prefix="KAFKA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bootstrap_servers: str = "localhost:9092"
    schema_registry_url: str = "http://localhost:8081"
    security_protocol: str = "PLAINTEXT"

    # SASL — only used when security_protocol is SASL_SSL
    sasl_mechanism: str = ""
    sasl_username: str = ""
    sasl_password: str = ""

    # Producer tuning
    producer_acks: str = "all"
    producer_enable_idempotence: bool = True
    producer_delivery_timeout_ms: int = 30_000
    producer_max_block_ms: int = 10_000

    # Consumer tuning
    consumer_auto_offset_reset: str = "earliest"
    consumer_max_poll_interval_ms: int = 300_000
    consumer_session_timeout_ms: int = 45_000

    def base_producer_config(self) -> dict[str, object]:
        """Return confluent-kafka Producer config dict."""
        cfg: dict[str, object] = {
            "bootstrap.servers": self.bootstrap_servers,
            "acks": self.producer_acks,
            "enable.idempotence": self.producer_enable_idempotence,
            "delivery.timeout.ms": self.producer_delivery_timeout_ms,
            "max.block.ms": self.producer_max_block_ms,
        }
        self._add_sasl(cfg)
        return cfg

    def base_consumer_config(self, group_id: str) -> dict[str, object]:
        """Return confluent-kafka Consumer config dict."""
        cfg: dict[str, object] = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": group_id,
            "enable.auto.commit": False,
            "auto.offset.reset": self.consumer_auto_offset_reset,
            "max.poll.interval.ms": self.consumer_max_poll_interval_ms,
            "session.timeout.ms": self.consumer_session_timeout_ms,
        }
        self._add_sasl(cfg)
        return cfg

    def _add_sasl(self, cfg: dict[str, object]) -> None:
        if self.security_protocol != "PLAINTEXT":
            cfg["security.protocol"] = self.security_protocol
        if self.sasl_mechanism:
            cfg["sasl.mechanism"] = self.sasl_mechanism
        if self.sasl_username:
            cfg["sasl.username"] = self.sasl_username
        if self.sasl_password:
            cfg["sasl.password"] = self.sasl_password
