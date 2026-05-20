# harmoni Kafka Topics

Reference documentation for all Kafka topics in the harmoni CEP pipeline.
See ADR 0003 for the architectural decision record.

---

## Topic Overview

| Topic | Partitions | Replication | Retention | Schema Subject |
|-------|------------|-------------|-----------|----------------|
| `harmoni.dlq` | 3 | 1 (local) / 3 (prod) | 90 days | `harmoni.dlq-value` |
| `harmoni.web.pageview` | 6 | 1 (local) / 3 (prod) | 30 days | `harmoni.web.pageview-value` |
| `harmoni.email.engagement` | 6 | 1 (local) / 3 (prod) | 30 days | `harmoni.email.engagement-value` |
| `harmoni.crm.contact_activity` | 6 | 1 (local) / 3 (prod) | 30 days | `harmoni.crm.contact_activity-value` |
| `harmoni.webinar.attendance` | 6 | 1 (local) / 3 (prod) | 30 days | `harmoni.webinar.attendance-value` |

> **Production replication factor is 3** (set in `infra/terraform/modules/kafka/main.tf`).
> The docker-compose local dev stack uses replication factor 1 (single broker).

---

## Partitioning Strategy

All topics are **partitioned by `account_domain`** (the normalized company email domain).
This guarantees that all events for a single account always land on the same partition,
enabling ordered, per-account processing in downstream consumers without global coordination.

Example: all signals from `acme.com` go to the same partition, so the Intent Network
Model can maintain a consistent state window for that account.

---

## Topic Details

### `harmoni.dlq`

Dead-letter queue for all unprocessable messages. Every record is wrapped in a
`DLQEnvelope` Avro schema with:
- `source_topic` — where the failure originated
- `failure_stage` — `SERIALIZATION | SCHEMA_VALIDATION | PRODUCE | CONSUME | PROCESSING`
- `error_class` + `error_message` — exception details
- `original_key` + `original_value` — raw bytes for replay or manual inspection

**Monitoring**: Alert on consumer lag > 0 for group `harmoni.dlq.monitor`.
Any DLQ message indicates a pipeline defect that must be investigated.

---

### `harmoni.web.pageview`

Web analytics pageview events, sourced from server-side pixel or log ingestion.

**Key fields for intent scoring:**
- `page_category` — `PRICING` and `PRODUCT` pages carry highest intent weight
- `time_on_page_seconds` — extended sessions on pricing pages are strong signals
- `session_id` — used to reconstruct session journeys

**Producer**: `WebAnalyticsConnector`
**Consumer groups**: `harmoni.scoring.intent`, `harmoni.identity.resolver`

---

### `harmoni.email.engagement`

Email platform engagement events (opens, clicks, replies, unsubscribes).

**Key fields for fatigue scoring:**
- `engagement_type` — `UNSUBSCRIBED`, `BOUNCED`, `SPAM_REPORTED` set `is_negative=true`
  and directly increase the account fatigue score
- `campaign_id` — links to outreach frequency calculation

**Producer**: `EmailEngagementConnector`
**Consumer groups**: `harmoni.scoring.fatigue`, `harmoni.scoring.intent`

---

### `harmoni.crm.contact_activity`

CRM activity events from HubSpot or Salesforce webhooks.

**Key fields:**
- `activity_type` — `MEETING_BOOKED` and `MEETING_COMPLETED` are the strongest
  positive engagement signals in the entire pipeline
- `deal_stage` — deal stage changes feed the ChurnPredictor feature set
- `lifecycle_stage_changed` — indicates progression through buying process

**Producer**: `CRMActivityConnector`
**Consumer groups**: `harmoni.scoring.intent`, `harmoni.scoring.churn`

---

### `harmoni.webinar.attendance`

Webinar registration and attendance events (Zoom, GoToWebinar).

**Key fields:**
- `attendance_type` — `ATTENDED_LIVE` is weighted 3× stronger than `REGISTERED`
- `attendance_duration_minutes` — partial attendance (< 20% of session) is discounted
- `questions_asked` — active participation is the strongest single webinar signal
- `webinar_topic` — `PRODUCT_DEMO` events trigger NBA evaluation immediately

**Producer**: `WebinarAttendanceConnector`
**Consumer groups**: `harmoni.scoring.intent`

---

## Schema Compatibility Mode

All subjects use **`BACKWARD`** compatibility:
- New consumers can read messages produced by old producers
- Adding optional fields with defaults is always safe
- Removing required fields or changing field types requires a schema migration

**To evolve a schema:**
1. Update the `.avsc` file in `ingestion/schemas/`
2. Ensure the change is backward-compatible (new fields must have `default`)
3. Run `python -m ingestion.kafka.schema_registry --register` in staging
4. Run the integration test suite before deploying to prod

---

## Local Development

```bash
# Start the full stack
docker-compose up -d kafka schema-registry

# Create all topics
python -c "from ingestion.kafka.admin import ensure_topics_exist; ensure_topics_exist('localhost:9092')"

# Register all schemas
python -c "from ingestion.kafka.schema_registry import SchemaRegistryManager; SchemaRegistryManager('http://localhost:8081').register_all()"

# Browse topics and messages
open http://localhost:8080  # Kafka UI
```

---

## Topic Configuration Reference

```python
from ingestion.kafka.topics import ALL_TOPICS, TOPIC_BY_NAME

# Print all topic configs
for t in ALL_TOPICS:
    print(f"{t.name}: {t.partitions}p / {t.replication_factor}r / {t.retention_ms}ms")
```
