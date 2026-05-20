# 0003: Kafka with Avro Schema Registry as the CEP Event Backbone
**Status**: Accepted
**Date**: 2026-05-17

## Context

harmoni ingests signals from heterogeneous sources (CRM webhooks, web analytics pixels, email engagement callbacks, webinar attendance events). These arrive at different rates, in different formats, from systems we do not control. We need a durable, ordered, replayable event log that:
- Enforces a stable schema contract across producers and consumers
- Supports at-least-once delivery guarantees
- Scales to millions of events per day without architectural changes
- Provides a dead-letter queue (DLQ) for schema-invalid or unprocessable messages

Options considered:
1. **Postgres LISTEN/NOTIFY** — too low-throughput; no replay; tight coupling to operational DB.
2. **RabbitMQ** — good for task queues; weaker replay semantics; schema enforcement requires custom middleware.
3. **Kafka + Confluent Schema Registry** — industry standard for CEP; native at-least-once delivery; Avro schema enforcement at the broker level; built-in replay via offset reset.

## Decision

All real-time event ingestion flows through **Apache Kafka** with **Confluent Schema Registry** for Avro schema validation.

Topic naming convention: `harmoni.{source}.{event_type}`

Canonical topics defined in Sprint 1:
- `harmoni.web.pageview`
- `harmoni.email.engagement`
- `harmoni.crm.contact_activity`
- `harmoni.webinar.attendance`
- `harmoni.dlq` — dead-letter queue for schema-invalid messages

Rules:
- Every topic has a registered Avro schema in `ingestion/schemas/`. No schema = no production.
- Schema compatibility mode: `BACKWARD` — new consumers can read old messages; producers must not break existing fields.
- The CI pipeline validates all `.avsc` files on every PR.
- Messages that fail schema validation or cannot be processed route to `harmoni.dlq` with an error envelope (original bytes + error reason + source topic).

Partition strategy:
- All topics partitioned by `account_domain` (normalized) to guarantee ordering of signals per account.
- Default: 6 partitions, replication factor 3 in production.

## Consequences

- **Positive**: Schema contract is enforced at the broker; no producer can silently break downstream consumers.
- **Positive**: Full event replay from any offset supports backfill and re-scoring without re-ingestion.
- **Negative**: Schema Registry is a new infrastructure dependency; local development requires the Confluent Platform Docker image.
- **Operational**: Any new event type requires a new `.avsc` schema registered before the producer is deployed. This is a deployment gate, not a suggestion.
