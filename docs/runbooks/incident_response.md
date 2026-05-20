# Incident Response Runbook — Sev-1
**System**: harmoni Revenue Intelligence Platform  
**Version**: 1.0 — Sprint 10  
**Oncall rotation**: PagerDuty schedule `harmoni-oncall`

---

## Severity Definitions

| Severity | Definition | Response SLA |
|----------|------------|-------------|
| **Sev-1** | Data loss, complete service unavailability, or CRITICAL fatigue account not receiving cooldown | 15 min acknowledge, 1 hour resolve |
| **Sev-2** | Degraded scoring (stale > 4h), webhook delivery failure, API error rate > 5% | 30 min acknowledge, 4 hour resolve |
| **Sev-3** | Individual DAG failure, elevated latency, non-critical alert firing | Business hours |

---

## Sev-1 Triggers

These PagerDuty alerts auto-page the oncall engineer:

1. `KafkaConsumerLagCritical` — consumer group > 5 min behind
2. `AirflowDAGFailed` — any scoring DAG
3. `APIErrorRateHigh` — 5xx > 1% for > 5 min
4. `NBADispatchFailureCritical` — CRITICAL fatigue account not dispatched

---

## Response Protocol

### 1. Acknowledge (0–15 min)

```bash
# Confirm you're on it in Slack #incidents
# Acknowledge in PagerDuty (stops escalation)

# Quick health check
curl https://api.harmoni.io/health | jq .
kubectl get pods -n harmoni-prod
```

### 2. Diagnose

**API error rate spike**:
```bash
# Get recent error logs
kubectl logs -n harmoni-prod deploy/harmoni-api --tail=200 | grep '"level":"ERROR"'

# Check which endpoints are failing
# Grafana → harmoni overview → "API 5xx Error Rate" panel
```

**Kafka consumer lag**:
```bash
# Check which consumer group is lagging
kubectl exec -n harmoni-prod deploy/kafka-consumer -- \
  kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --describe --group harmoni-signals

# Check consumer pod health
kubectl describe pod -n harmoni-prod -l app=harmoni-consumer
```

**Airflow DAG failure**:
```bash
# Access Airflow UI
kubectl port-forward -n harmoni-prod svc/airflow-webserver 8080:8080
# Open http://localhost:8080 → find failed DAG → check task logs

# Manually trigger a DAG run after fixing
airflow dags trigger dag_fatigue_score_refresh
```

**CRITICAL fatigue account not dispatched**:
```bash
# Find the account
psql $DATABASE_URL -c "
  SELECT account_domain, score, severity, computed_at
  FROM account_fatigue_scores
  WHERE severity = 'CRITICAL'
  ORDER BY computed_at DESC
  LIMIT 10;
"

# Check Redis cooldown
redis-cli -u $REDIS_URL GET cooldown:account:{account_id}

# Check NBA dispatch log
kubectl logs -n harmoni-prod deploy/harmoni-api | \
  grep '"event":"audit_write"' | grep 'nba' | tail -20
```

### 3. Mitigate

**API overloaded** → scale out:
```bash
kubectl scale deploy harmoni-api -n harmoni-prod --replicas=6
```

**Kafka lag** → scale consumers:
```bash
kubectl scale deploy harmoni-consumer -n harmoni-prod --replicas=4
```

**DAG stuck in running state** → clear and retry:
```bash
airflow tasks clear dag_fatigue_score_refresh -t compute_fatigue_scores --yes
airflow dags trigger dag_fatigue_score_refresh
```

**Redis unavailable (fail-open)** → cooldowns are not enforced:
- This is a Sev-1 per the fail-safe design (Section 5 of `scoring/fatigue/cooldown.py`)
- Notify customer success: "Account protection is temporarily degraded"
- Restart Redis pod or failover to replica

### 4. Resolve and Post-Mortem

- [ ] Confirm all alerts have resolved in PagerDuty
- [ ] Verify account scores are fresh: `GET /health` shows `degraded: false`
- [ ] Post incident summary in `#incidents` within 2 hours
- [ ] Schedule blameless post-mortem within 48 hours
- [ ] Write post-mortem doc in `docs/post-mortems/YYYY-MM-DD-{slug}.md`
- [ ] File any follow-up issues in GitHub with label `sev-1-followup`

---

## Communication Templates

**Partner-facing status update** (post in `#dp-{partner-slug}` every 30 min):
```
[STATUS UPDATE] We're investigating an issue affecting {feature}.
Impact: {what partners might see}. Our team is actively working on a fix.
Next update: {time}.
```

**Resolution notice**:
```
[RESOLVED] The issue affecting {feature} has been resolved as of {time}.
Root cause: {one sentence}. We'll share a full post-mortem by {date}.
```
