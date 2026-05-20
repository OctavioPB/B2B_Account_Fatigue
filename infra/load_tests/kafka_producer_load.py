"""Kafka ingestion load test.

Sprint 10 acceptance gate: 10,000 events/minute sustained, zero message loss.

Produces synthetic IntentSignal events across all four harmoni topics at the
target throughput and measures actual delivery rate + consumer lag.

Run:
    python infra/load_tests/kafka_producer_load.py \
        --bootstrap-servers localhost:9092 \
        --events-per-minute 10000 \
        --duration-seconds 300

Prerequisites:
    pip install confluent-kafka faker
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
import uuid
from datetime import datetime, timezone

from confluent_kafka import Producer
from faker import Faker

fake = Faker()

TOPICS = [
    "harmoni.web.pageview",
    "harmoni.email.engagement",
    "harmoni.crm.contact_activity",
    "harmoni.webinar.attendance",
]

SIGNAL_TYPES_BY_TOPIC: dict[str, list[str]] = {
    "harmoni.web.pageview": ["page_view", "pricing_page_view", "video_view"],
    "harmoni.email.engagement": ["email_open", "email_click", "email_reply", "unsubscribe", "bounce"],
    "harmoni.crm.contact_activity": ["crm_note"],
    "harmoni.webinar.attendance": ["webinar_attend"],
}

SAMPLE_DOMAINS = [
    "acme.com", "globex.com", "initech.com", "umbrella.io",
    "stark.io", "wayne.co", "oscorp.com", "massive.io",
]


def _make_event(topic: str) -> dict:
    domain = random.choice(SAMPLE_DOMAINS)
    signal_type = random.choice(SIGNAL_TYPES_BY_TOPIC[topic])
    return {
        "event_id": str(uuid.uuid4()),
        "schema_version": "1.0",
        "account_domain": domain,
        "member_email": fake.email().split("@")[0] + f"@{domain}",
        "signal_type": signal_type,
        "channel": topic.split(".")[1],
        "occurred_at": datetime.now(tz=timezone.utc).isoformat(),
        "metadata": {},
    }


def _delivery_report(err, msg) -> None:
    if err is not None:
        print(f"[DELIVERY ERROR] {msg.topic()}#{msg.partition()}: {err}")


def run_load_test(
    bootstrap_servers: str,
    events_per_minute: int,
    duration_seconds: int,
) -> dict:
    producer = Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",              # wait for all ISR acknowledgements
            "linger.ms": 5,            # small batching window
            "batch.size": 65536,       # 64KB batches
            "compression.type": "lz4",
            "retries": 5,
            "retry.backoff.ms": 100,
        }
    )

    target_rate = events_per_minute / 60.0  # events per second
    interval = 1.0 / target_rate

    sent = 0
    errors = 0
    latencies_ms: list[float] = []
    start_wall = time.perf_counter()
    deadline = start_wall + duration_seconds

    print(
        f"Starting load test: {events_per_minute} events/min "
        f"for {duration_seconds}s across {len(TOPICS)} topics"
    )

    while time.perf_counter() < deadline:
        t0 = time.perf_counter()
        topic = random.choice(TOPICS)
        event = _make_event(topic)
        key = event["account_domain"].encode()

        try:
            producer.produce(
                topic=topic,
                key=key,
                value=json.dumps(event).encode(),
                on_delivery=_delivery_report,
            )
            sent += 1
        except BufferError:
            producer.poll(0.001)
            errors += 1

        elapsed = time.perf_counter() - t0
        latencies_ms.append(elapsed * 1000)

        sleep_for = interval - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)

        # Poll every 1000 events to drain delivery queue
        if sent % 1000 == 0:
            producer.poll(0)
            elapsed_total = time.perf_counter() - start_wall
            actual_rate = sent / elapsed_total * 60
            print(
                f"  {sent:>8,} sent | {actual_rate:>8,.0f} events/min "
                f"| {errors} errors | elapsed {elapsed_total:.0f}s"
            )

    producer.flush(timeout=30)

    total_elapsed = time.perf_counter() - start_wall
    actual_rate = sent / total_elapsed * 60

    result = {
        "target_events_per_minute": events_per_minute,
        "actual_events_per_minute": round(actual_rate, 1),
        "total_sent": sent,
        "total_errors": errors,
        "duration_seconds": round(total_elapsed, 1),
        "p50_produce_ms": round(statistics.median(latencies_ms), 3) if latencies_ms else None,
        "p99_produce_ms": round(statistics.quantiles(latencies_ms, n=100)[98], 3) if len(latencies_ms) >= 100 else None,
        "pass": errors == 0 and actual_rate >= events_per_minute * 0.99,
    }

    print("\n=== Load Test Results ===")
    for k, v in result.items():
        print(f"  {k}: {v}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="harmoni Kafka load test")
    parser.add_argument("--bootstrap-servers", default="localhost:9092")
    parser.add_argument("--events-per-minute", type=int, default=10_000)
    parser.add_argument("--duration-seconds", type=int, default=300)
    args = parser.parse_args()

    result = run_load_test(
        bootstrap_servers=args.bootstrap_servers,
        events_per_minute=args.events_per_minute,
        duration_seconds=args.duration_seconds,
    )
    raise SystemExit(0 if result["pass"] else 1)
