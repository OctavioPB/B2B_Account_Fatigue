# Setup & Deployment Debugging Reference

Issues encountered during initial environment setup after Sprint 10 completion. Each entry describes the symptom, root cause, and fix so future projects can resolve the same class of problem without re-diagnosing from scratch.

---

## 1. Confluent ZooKeeper healthcheck always failing

**Symptom**
`docker-compose up -d` reports `harmoni-zookeeper` as unhealthy. All dependent services (Kafka, Schema Registry) refuse to start.

**Root cause**
The healthcheck used the `ruok` 4-letter word command:
```yaml
test: ["CMD-SHELL", "echo ruok | nc localhost 2181 | grep imok"]
```
The Confluent ZooKeeper image restricts which 4LW commands are whitelisted. The intended fix was to add `ZOOKEEPER_4LW_COMMANDS_WHITELIST=ruok,srvr,stat` as an env var, but this silently fails: the image's init script translates `ZOOKEEPER_XYZ` env vars to ZooKeeper config properties by stripping the prefix and lowercasing, but the sed/awk pattern skips names that start with a digit. `4lw.commands.whitelist` starts with `4`, so the env var is never written to the config file.

**Fix**
Change the healthcheck to use `srvr`, which is whitelisted by default:
```yaml
healthcheck:
  test: ["CMD-SHELL", "echo srvr | nc localhost 2181 | grep -q 'Zookeeper version'"]
  interval: 10s
  timeout: 5s
  retries: 5
```

**Applies to**: any project using `confluentinc/cp-zookeeper`. Do not rely on env var injection to whitelist 4LW commands.

---

## 2. `uv pip install` fails — no virtual environment

**Symptom**
```
error: No virtual environment found; run `uv venv` to create an environment
```

**Root cause**
`uv pip install` requires an active virtual environment. Unlike `pip`, `uv` does not fall back to the system Python or create an env automatically.

**Fix**
```bash
uv venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows
uv pip install -e ".[all,dev]"
```

---

## 3. hatchling fails to find packages in monorepo

**Symptom**
After `uv pip install -e ".[all,dev]"` succeeds, imports fail at runtime because hatchling didn't detect any packages during the editable install.

**Root cause**
hatchling's auto-discovery looks for a directory that matches the project name (e.g. a `harmoni/` directory). In a monorepo where top-level directories are service names (`api/`, `scoring/`, `orchestrator/`, etc.), no single directory matches, so hatchling installs nothing.

**Fix**
Add an explicit packages list to `pyproject.toml`:
```toml
[tool.hatch.build.targets.wheel]
packages = ["api", "ingestion", "scoring", "orchestrator", "identity", "pipelines"]
```

**Applies to**: any Python monorepo using hatchling where the top-level service directories don't match the project name.

---

## 4. `psql` command not available on Windows

**Symptom**
```
psql: The term 'psql' is not recognized as the name of a cmdlet...
```

**Root cause**
PostgreSQL client tools are not installed on the host machine. The PostgreSQL instance runs inside Docker.

**Fix**
Route all `psql` commands through the running container:
```powershell
Get-Content api/migrations/001_tenants_webhooks.sql | docker exec -i harmoni-postgres psql -U harmoni -d harmoni
```
Or with a shell here-string for multiple files:
```powershell
docker exec -i harmoni-postgres psql -U harmoni -d harmoni -f - < api/migrations/001_tenants_webhooks.sql
```

**Note**: README/setup instructions must use the `docker exec -i` form, not bare `psql`, for portability on Windows developer machines.

---

## 5. Migration fails — columns reference tables that don't exist yet

**Symptom**
```
ERROR: column "is_active" of relation "accounts" does not exist
ERROR: column "arr_usd" does not exist
ERROR: relation "account_cooldowns" does not exist
```

**Root cause**
An index migration (`002_indexes.sql`) was written against an assumed schema that diverged from the actual DDL. Specific mismatches found:

| File reference | Actual column/table |
|---|---|
| `accounts.is_active` | column does not exist on `accounts` |
| `accounts.arr_usd` | column is `arr_band` |
| `committee_members(account_domain)` | FK column is `account_id` |
| `committee_members(is_current)` | column is `is_active` |
| `account_cooldowns` | table not created until a later sprint |

**Fix**
Audit index migrations against `CREATE TABLE` statements before running. For each index, verify:
- the table exists in an earlier migration
- every column name matches exactly
- the migration file runs *after* all tables it references

**Run order for this project**:
```
001_tenants_webhooks.sql
identity/migrations/*.sql
scoring/migrations/*.sql
orchestrator/migrations/*.sql
002_indexes.sql
003_audit_log.sql
```

---

## 6. FastAPI 0.136.1 — AssertionError on 204 DELETE responses

**Symptom**
```
AssertionError: Status code 204 must not have a response body
```
Raised at startup when FastAPI introspects routes, not at request time.

**Root cause**
FastAPI 0.136.1 added a stricter validation that 204 No Content responses must not define a response body type. A route returning `None` with `status_code=204` still generates a response schema, which triggers the assertion.

**Fix**
Add `response_class=Response` to the decorator and return an explicit `Response` object:
```python
from fastapi.responses import Response

@router.delete("/{id}", status_code=204, response_class=Response)
async def delete_item(id: str) -> Response:
    await service.delete(id)
    return Response(status_code=204)
```

**Applies to**: any FastAPI project on ≥0.115 using `status_code=204` on DELETE endpoints.

---

## 7. Pydantic `ValidationError` — required env var not in `.env.example`

**Symptom**
```
pydantic_settings.main.SettingsError: 1 validation error for Settings
harmoni_admin_token
  Field required [type=missing, ...]
```

**Root cause**
`Settings` declared `harmoni_admin_token: str` as a required field, but it was never added to `.env.example`. When a developer copies `.env.example` to `.env` (the standard first step), the required variable is missing and the application fails to start.

**Fix**
Every required `Settings` field must have a corresponding entry in `.env.example` with a placeholder value:
```dotenv
HARMONI_ADMIN_TOKEN=change-me-in-production-use-openssl-rand-hex-32
```
Generate the real value for `.env`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Rule for future projects**: treat `.env.example` as a contract. Any field in `Settings` without a default value must appear in `.env.example` or the README setup steps will break silently.

---

## 8. Next.js 14 — `next.config.ts` not supported

**Symptom**
```
Error: Configuring Next.js via 'next.config.ts' is not supported. Use 'next.config.js' or 'next.config.mjs'.
```

**Root cause**
TypeScript config files for Next.js (`next.config.ts`) require Next.js 15+. The project was on Next.js 14.

**Fix**
Rename `next.config.ts` → `next.config.mjs` and replace the TypeScript type import with a JSDoc annotation:
```js
// next.config.mjs
/** @type {import('next').NextConfig} */
const nextConfig = {
  // ...
};

export default nextConfig;
```

**Applies to**: any project on Next.js 14 that uses a `.ts` config. Check `package.json` `next` version before initialising a TypeScript config file.

---

## Summary table

| # | Area | Symptom keyword | Root cause class |
|---|---|---|---|
| 1 | Docker / Confluent | ZooKeeper unhealthy | Env var name starts with digit, silently ignored by init script |
| 2 | Python / uv | No virtual environment | `uv pip` requires explicit venv creation |
| 3 | Python / hatchling | Packages not installed | Monorepo dirs don't match project name; auto-discovery fails |
| 4 | Windows / PostgreSQL | `psql` not recognized | CLI tools not installed on host; must route through Docker |
| 5 | SQL migrations | Column does not exist | Index migration written against assumed schema, not actual DDL |
| 6 | FastAPI 0.136.1 | AssertionError on 204 | Breaking change: 204 routes must use explicit `response_class=Response` |
| 7 | Pydantic Settings | Field required | Required env var missing from `.env.example` |
| 8 | Next.js 14 | `next.config.ts` not supported | TypeScript config requires Next.js 15+ |
